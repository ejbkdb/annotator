# backend/audio_feature_processor.py
import numpy as np
import librosa
import scipy.signal
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import joblib
import logging
from typing import Dict, List, Tuple, Optional, Any
import tensorflow as tf
from pathlib import Path
import pickle
import json
from dataclasses import dataclass, asdict
from datetime import datetime
import concurrent.futures
import hashlib

logger = logging.getLogger(__name__)

@dataclass
class AudioFeatures:
    """Container for extracted audio features."""
    mfcc: np.ndarray
    spectral_centroid: np.ndarray
    spectral_rolloff: np.ndarray
    spectral_bandwidth: np.ndarray
    zero_crossing_rate: np.ndarray
    rms_energy: np.ndarray
    tempo: float
    chroma: np.ndarray
    mel_spectrogram: np.ndarray
    tonnetz: np.ndarray
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'mfcc': self.mfcc.tolist(),
            'spectral_centroid': self.spectral_centroid.tolist(),
            'spectral_rolloff': self.spectral_rolloff.tolist(),
            'spectral_bandwidth': self.spectral_bandwidth.tolist(),
            'zero_crossing_rate': self.zero_crossing_rate.tolist(),
            'rms_energy': self.rms_energy.tolist(),
            'tempo': float(self.tempo),
            'chroma': self.chroma.tolist(),
            'mel_spectrogram': self.mel_spectrogram.tolist(),
            'tonnetz': self.tonnetz.tolist()
        }
    
    def to_feature_vector(self) -> np.ndarray:
        """Flatten all features into a single vector."""
        features = []
        
        # Add statistical summaries of time-varying features
        for feat in [self.mfcc, self.spectral_centroid, self.spectral_rolloff,
                    self.spectral_bandwidth, self.zero_crossing_rate, 
                    self.rms_energy, self.chroma, self.tonnetz]:
            if feat.ndim > 1:
                # For 2D features (e.g., MFCC), compute stats per coefficient
                features.extend(np.mean(feat, axis=1))
                features.extend(np.std(feat, axis=1))
                features.extend(np.max(feat, axis=1))
                features.extend(np.min(feat, axis=1))
            else:
                # For 1D features
                features.extend([np.mean(feat), np.std(feat), 
                               np.max(feat), np.min(feat)])
        
        # Add tempo
        features.append(self.tempo)
        
        return np.array(features)

class AudioFeatureProcessor:
    """Extract and process audio features for ML models."""
    
    def __init__(self, sample_rate: int = 48000, 
                 n_mfcc: int = 13,
                 n_fft: int = 2048,
                 hop_length: int = 512):
        self.sample_rate = sample_rate
        self.n_mfcc = n_mfcc
        self.n_fft = n_fft
        self.hop_length = hop_length
        
        # Feature extraction parameters
        self.mel_bins = 128
        self.chroma_bins = 12
        
        # Initialize scalers (will be loaded or fitted)
        self.scaler = None
        self.pca = None
        
        # Model cache
        self.models = {}
        
    def extract_features(self, audio: np.ndarray, 
                        sr: Optional[int] = None) -> AudioFeatures:
        """Extract comprehensive audio features."""
        if sr is None:
            sr = self.sample_rate
            
        # Ensure audio is float32 and normalized
        audio = audio.astype(np.float32)
        if np.max(np.abs(audio)) > 1.0:
            audio = audio / 32768.0  # Assuming 16-bit input
            
        # Time-domain features
        zcr = librosa.feature.zero_crossing_rate(audio, 
                                                frame_length=self.n_fft,
                                                hop_length=self.hop_length)[0]
        
        rms = librosa.feature.rms(y=audio, 
                                 frame_length=self.n_fft,
                                 hop_length=self.hop_length)[0]
        
        # Spectral features
        stft = np.abs(librosa.stft(audio, n_fft=self.n_fft, 
                                   hop_length=self.hop_length))
        
        spectral_centroid = librosa.feature.spectral_centroid(
            S=stft, sr=sr, hop_length=self.hop_length)[0]
        
        spectral_rolloff = librosa.feature.spectral_rolloff(
            S=stft, sr=sr, hop_length=self.hop_length)[0]
        
        spectral_bandwidth = librosa.feature.spectral_bandwidth(
            S=stft, sr=sr, hop_length=self.hop_length)[0]
        
        # MFCC
        mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=self.n_mfcc,
                                    n_fft=self.n_fft, 
                                    hop_length=self.hop_length)
        
        # Mel spectrogram
        mel_spec = librosa.feature.melspectrogram(
            y=audio, sr=sr, n_mels=self.mel_bins,
            n_fft=self.n_fft, hop_length=self.hop_length)
        mel_spec_db = librosa.power_to_db(mel_spec, ref=np.max)
        
        # Chroma features
        chroma = librosa.feature.chroma_stft(S=stft, sr=sr, 
                                            n_chroma=self.chroma_bins,
                                            hop_length=self.hop_length)
        
        # Tonnetz (tonal centroid features)
        tonnetz = librosa.feature.tonnetz(y=audio, sr=sr,
                                         hop_length=self.hop_length)
        
        # Tempo estimation
        tempo, _ = librosa.beat.beat_track(y=audio, sr=sr,
                                          hop_length=self.hop_length)
        
        return AudioFeatures(
            mfcc=mfcc,
            spectral_centroid=spectral_centroid,
            spectral_rolloff=spectral_rolloff,
            spectral_bandwidth=spectral_bandwidth,
            zero_crossing_rate=zcr,
            rms_energy=rms,
            tempo=float(tempo),
            chroma=chroma,
            mel_spectrogram=mel_spec_db,
            tonnetz=tonnetz
        )
    
    def extract_window_features(self, audio: np.ndarray, 
                              window_size: float = 1.0,
                              overlap: float = 0.5) -> List[AudioFeatures]:
        """Extract features from overlapping windows."""
        window_samples = int(window_size * self.sample_rate)
        hop_samples = int((1 - overlap) * window_samples)
        
        features_list = []
        
        for start in range(0, len(audio) - window_samples + 1, hop_samples):
            window = audio[start:start + window_samples]
            features = self.extract_features(window)
            features_list.append(features)
            
        return features_list
    
    def compute_delta_features(self, features: AudioFeatures) -> Dict[str, np.ndarray]:
        """Compute delta (velocity) and delta-delta (acceleration) features."""
        delta_features = {}
        
        # Compute deltas for time-varying features
        for name, feat in [
            ('mfcc', features.mfcc),
            ('spectral_centroid', features.spectral_centroid),
            ('chroma', features.chroma)
        ]:
            if feat.ndim == 1:
                feat = feat.reshape(1, -1)
                
            delta = librosa.feature.delta(feat)
            delta_delta = librosa.feature.delta(feat, order=2)
            
            delta_features[f'{name}_delta'] = delta
            delta_features[f'{name}_delta_delta'] = delta_delta
            
        return delta_features
    
    def load_model(self, model_path: str, model_type: str = 'tensorflow') -> Any:
        """Load a trained ML model."""
        model_path = Path(model_path)
        
        if model_path in self.models:
            return self.models[model_path]
            
        try:
            if model_type == 'tensorflow':
                model = tf.keras.models.load_model(model_path)
            elif model_type == 'sklearn':
                model = joblib.load(model_path)
            elif model_type == 'pickle':
                with open(model_path, 'rb') as f:
                    model = pickle.load(f)
            else:
                raise ValueError(f"Unknown model type: {model_type}")
                
            self.models[model_path] = model
            logger.info(f"Loaded model from {model_path}")
            return model
            
        except Exception as e:
            logger.error(f"Failed to load model from {model_path}: {str(e)}")
            raise
    
    def classify_audio(self, audio: np.ndarray, 
                      model_path: str,
                      model_type: str = 'tensorflow',
                      preprocess: bool = True) -> Dict[str, Any]:
        """Classify audio using a trained model."""
        # Extract features
        features = self.extract_features(audio)
        feature_vector = features.to_feature_vector()
        
        # Preprocess if needed
        if preprocess and self.scaler:
            feature_vector = self.scaler.transform(feature_vector.reshape(1, -1))
            
        if preprocess and self.pca:
            feature_vector = self.pca.transform(feature_vector)
            
        # Load and apply model
        model = self.load_model(model_path, model_type)
        
        if model_type == 'tensorflow':
            # Ensure correct shape for neural network
            if feature_vector.ndim == 1:
                feature_vector = feature_vector.reshape(1, -1)
            predictions = model.predict(feature_vector)
            
            # Get class probabilities
            if predictions.shape[1] > 1:
                class_probs = predictions[0]
                predicted_class = np.argmax(class_probs)
                confidence = float(class_probs[predicted_class])
            else:
                predicted_class = int(predictions[0, 0] > 0.5)
                confidence = float(predictions[0, 0] if predicted_class else 1 - predictions[0, 0])
                
        else:
            # Sklearn model
            predicted_class = model.predict(feature_vector)[0]
            
            # Get confidence if available
            if hasattr(model, 'predict_proba'):
                probs = model.predict_proba(feature_vector)[0]
                confidence = float(np.max(probs))
            else:
                confidence = 1.0
                
        return {
            'predicted_class': int(predicted_class),
            'confidence': confidence,
            'features': features.to_dict(),
            'feature_vector': feature_vector.tolist()
        }
    
    def process_batch(self, audio_files: List[str], 
                     model_path: str,
                     output_dir: str,
                     num_workers: int = 4) -> Dict[str, Any]:
        """Process multiple audio files in parallel."""
        from backend.audio_processor import AudioProcessor
        audio_processor = AudioProcessor()
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = {
            'processed': 0,
            'failed': 0,
            'classifications': {},
            'errors': []
        }
        
        def process_file(file_path: str) -> Tuple[str, Dict[str, Any]]:
            try:
                # Load audio
                audio, sr = audio_processor.load_audio_file(file_path)
                
                # Resample if needed
                if sr != self.sample_rate:
                    audio = audio_processor.resample_audio(
                        audio, sr, self.sample_rate)
                
                # Classify
                result = self.classify_audio(audio, model_path)
                
                # Save results
                output_file = output_dir / f"{Path(file_path).stem}_features.json"
                with open(output_file, 'w') as f:
                    json.dump(result, f, indent=2)
                    
                return file_path, result
                
            except Exception as e:
                logger.error(f"Error processing {file_path}: {str(e)}")
                return file_path, {'error': str(e)}
        
        # Process files in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_file = {
                executor.submit(process_file, fp): fp 
                for fp in audio_files
            }
            
            for future in concurrent.futures.as_completed(future_to_file):
                file_path = future_to_file[future]
                _, result = future.result()
                
                if 'error' in result:
                    results['failed'] += 1
                    results['errors'].append({
                        'file': file_path,
                        'error': result['error']
                    })
                else:
                    results['processed'] += 1
                    results['classifications'][file_path] = result
                    
        return results
    
    def train_feature_normalizer(self, training_features: np.ndarray,
                               save_path: Optional[str] = None) -> None:
        """Train feature normalization on training data."""
        self.scaler = StandardScaler()
        self.scaler.fit(training_features)
        
        if save_path:
            joblib.dump(self.scaler, save_path)
            logger.info(f"Saved scaler to {save_path}")
    
    def train_pca(self, training_features: np.ndarray, 
                 n_components: int = 50,
                 save_path: Optional[str] = None) -> None:
        """Train PCA for dimensionality reduction."""
        self.pca = PCA(n_components=n_components)
        self.pca.fit(training_features)
        
        explained_var = np.sum(self.pca.explained_variance_ratio_)
        logger.info(f"PCA explains {explained_var:.2%} of variance with {n_components} components")
        
        if save_path:
            joblib.dump(self.pca, save_path)
            logger.info(f"Saved PCA to {save_path}")
    
    def compute_feature_hash(self, features: AudioFeatures) -> str:
        """Compute hash of features for caching."""
        feature_bytes = pickle.dumps(features.to_dict())
        return hashlib.sha256(feature_bytes).hexdigest()