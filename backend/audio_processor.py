# backend/audio_processor.py
import numpy as np
import soundfile as sf
import librosa
import scipy.signal
from pathlib import Path
import logging
from typing import Tuple, Optional, Dict, Any
import resampy
import warnings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AudioProcessor:
    """Production-ready audio processing with real DSP operations."""
    
    def __init__(self, target_sample_rate: int = 48000):
        self.target_sample_rate = target_sample_rate
        self.supported_formats = {'.wav', '.flac', '.mp3', '.ogg', '.m4a'}
        
    def load_audio_file(self, file_path: str, start_time: Optional[float] = None, 
                       duration: Optional[float] = None) -> Tuple[np.ndarray, int]:
        """
        Load audio file with optional time slicing.
        
        Args:
            file_path: Path to audio file
            start_time: Start time in seconds (None for beginning)
            duration: Duration in seconds (None for entire file)
            
        Returns:
            Tuple of (audio_samples, sample_rate)
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")
            
        if file_path.suffix.lower() not in self.supported_formats:
            raise ValueError(f"Unsupported format: {file_path.suffix}")
        
        try:
            # For WAV/FLAC, use soundfile for efficiency
            if file_path.suffix.lower() in {'.wav', '.flac'}:
                info = sf.info(file_path)
                original_sr = info.samplerate
                
                # Calculate frame positions
                start_frame = int(start_time * original_sr) if start_time else 0
                frames_to_read = int(duration * original_sr) if duration else -1
                
                # Read specific portion
                audio_data, sr = sf.read(file_path, start=start_frame, 
                                       frames=frames_to_read, dtype='float32')
            else:
                # For compressed formats, use librosa
                audio_data, sr = librosa.load(file_path, sr=None, 
                                             offset=start_time, 
                                             duration=duration)
                
            # Handle mono/stereo conversion
            if audio_data.ndim > 1:
                audio_data = np.mean(audio_data, axis=1)
                
            logger.info(f"Loaded {file_path.name}: {len(audio_data)} samples @ {sr}Hz")
            return audio_data, sr
            
        except Exception as e:
            logger.error(f"Failed to load {file_path}: {str(e)}")
            raise
    
    def resample_audio(self, audio: np.ndarray, orig_sr: int, 
                    target_sr: int) -> np.ndarray:
        """
        Resample audio to target sample rate using high-quality resampling.
        """
        if orig_sr == target_sr:
            return audio
            
        try:
            # Use resampy for high-quality resampling
            resampled = resampy.resample(audio, orig_sr, target_sr, 
                                        filter='kaiser_best')
            logger.info(f"Resampled from {orig_sr}Hz to {target_sr}Hz")
            return resampled
        except Exception as e:
            logger.error(f"Resampling failed: {str(e)}")
            # Fallback to scipy/librosa
            return librosa.resample(audio, orig_sr=orig_sr, target_sr=target_sr)
        
    def apply_bandpass_filter(self, audio: np.ndarray, sample_rate: int,
                            low_freq: float = 20.0, 
                            high_freq: float = 20000.0) -> np.ndarray:
        """
        Apply bandpass filter to remove unwanted frequencies.
        
        Args:
            audio: Input audio samples
            sample_rate: Sample rate
            low_freq: Low cutoff frequency (Hz)
            high_freq: High cutoff frequency (Hz)
            
        Returns:
            Filtered audio
        """
        nyquist = sample_rate / 2
        low_norm = low_freq / nyquist
        high_norm = high_freq / nyquist
        
        # Design Butterworth bandpass filter
        b, a = scipy.signal.butter(4, [low_norm, high_norm], btype='band')
        
        # Apply filter (using filtfilt for zero-phase)
        filtered = scipy.signal.filtfilt(b, a, audio)
        return filtered
    
    def remove_dc_offset(self, audio: np.ndarray) -> np.ndarray:
        """Remove DC offset from audio signal."""
        return audio - np.mean(audio)
    
    def normalize_audio(self, audio: np.ndarray, 
                       method: str = 'peak', 
                       target_level: float = 0.95) -> np.ndarray:
        """
        Normalize audio using specified method.
        
        Args:
            audio: Input audio
            method: 'peak' or 'rms'
            target_level: Target level (0-1)
            
        Returns:
            Normalized audio
        """
        if method == 'peak':
            max_val = np.max(np.abs(audio))
            if max_val > 0:
                return audio * (target_level / max_val)
        elif method == 'rms':
            rms = np.sqrt(np.mean(audio**2))
            if rms > 0:
                return audio * (target_level / rms)
        return audio
    
    def detect_silence(self, audio: np.ndarray, sample_rate: int,
                      threshold_db: float = -40.0,
                      min_silence_duration: float = 0.1) -> np.ndarray:
        """
        Detect silence regions in audio.
        
        Args:
            audio: Input audio
            sample_rate: Sample rate
            threshold_db: Silence threshold in dB
            min_silence_duration: Minimum silence duration in seconds
            
        Returns:
            Boolean mask where True indicates silence
        """
        # Convert to power and then dB
        power = audio ** 2
        power_db = 10 * np.log10(power + 1e-10)
        
        # Initial silence mask
        silence_mask = power_db < threshold_db
        
        # Remove short non-silence regions (morphological closing)
        min_samples = int(min_silence_duration * sample_rate)
        kernel = np.ones(min_samples)
        silence_mask = scipy.signal.convolve(silence_mask.astype(float), 
                                            kernel, mode='same') > min_samples/2
        
        return silence_mask
    
    def extract_audio_features(self, audio: np.ndarray, 
                             sample_rate: int) -> Dict[str, Any]:
        """
        Extract comprehensive audio features for analysis.
        
        Args:
            audio: Input audio
            sample_rate: Sample rate
            
        Returns:
            Dictionary of features
        """
        features = {}
        
        # Time-domain features
        features['rms'] = float(np.sqrt(np.mean(audio**2)))
        features['peak_amplitude'] = float(np.max(np.abs(audio)))
        features['zero_crossing_rate'] = float(np.mean(librosa.zero_crossings(audio)))
        features['duration_seconds'] = len(audio) / sample_rate
        
        # Spectral features
        stft = np.abs(librosa.stft(audio))
        features['spectral_centroid'] = float(np.mean(librosa.feature.spectral_centroid(S=stft, sr=sample_rate)))
        features['spectral_rolloff'] = float(np.mean(librosa.feature.spectral_rolloff(S=stft, sr=sample_rate)))
        features['spectral_bandwidth'] = float(np.mean(librosa.feature.spectral_bandwidth(S=stft, sr=sample_rate)))
        
        # MFCC features
        mfccs = librosa.feature.mfcc(y=audio, sr=sample_rate, n_mfcc=13)
        features['mfcc_mean'] = mfccs.mean(axis=1).tolist()
        features['mfcc_std'] = mfccs.std(axis=1).tolist()
        
        # Tempo and beat tracking
        tempo, beats = librosa.beat.beat_track(y=audio, sr=sample_rate)
        features['tempo'] = float(tempo)
        features['beat_count'] = len(beats)
        
        return features
    
    def compute_spectrogram(self, audio: np.ndarray, sample_rate: int,
                          n_fft: int = 2048, hop_length: int = 512,
                          window: str = 'hann') -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Compute spectrogram using STFT.
        
        Args:
            audio: Input audio
            sample_rate: Sample rate
            n_fft: FFT size
            hop_length: Hop length between frames
            window: Window function
            
        Returns:
            Tuple of (spectrogram_magnitude, frequencies, times)
        """
        # Compute STFT
        stft = librosa.stft(audio, n_fft=n_fft, hop_length=hop_length, 
                           window=window)
        
        # Get magnitude spectrogram
        magnitude = np.abs(stft)
        
        # Generate frequency and time axes
        frequencies = librosa.fft_frequencies(sr=sample_rate, n_fft=n_fft)
        times = librosa.frames_to_time(np.arange(magnitude.shape[1]), 
                                      sr=sample_rate, hop_length=hop_length)
        
        return magnitude, frequencies, times
    
    def save_audio(self, audio: np.ndarray, sample_rate: int, 
                  output_path: str, format: str = 'wav',
                  bit_depth: int = 16) -> None:
        """
        Save audio to file with specified format and quality.
        
        Args:
            audio: Audio samples to save
            sample_rate: Sample rate
            output_path: Output file path
            format: Output format ('wav', 'flac', etc.)
            bit_depth: Bit depth for output (16, 24, 32)
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Ensure audio is in correct range
        if audio.dtype == np.float32 or audio.dtype == np.float64:
            # Clip to prevent overflow
            audio = np.clip(audio, -1.0, 1.0)
        
        # Set subtype based on bit depth
        subtype_map = {
            16: 'PCM_16',
            24: 'PCM_24',
            32: 'PCM_32'
        }
        subtype = subtype_map.get(bit_depth, 'PCM_16')
        
        try:
            sf.write(output_path, audio, sample_rate, 
                    format=format.upper(), subtype=subtype)
            logger.info(f"Saved audio: {output_path} ({format}, {bit_depth}-bit)")
        except Exception as e:
            logger.error(f"Failed to save audio to {output_path}: {str(e)}")
            raise
    
    def convert_audio_format(self, input_path: str, output_path: str,
                           output_format: str = 'wav',
                           target_sample_rate: Optional[int] = None,
                           bit_depth: int = 16) -> None:
        """
        Convert audio file to different format with optional resampling.
        
        Args:
            input_path: Input file path
            output_path: Output file path
            output_format: Target format
            target_sample_rate: Target sample rate (None to keep original)
            bit_depth: Output bit depth
        """
        # Load audio
        audio, sr = self.load_audio_file(input_path)
        
        # Resample if needed
        if target_sample_rate and sr != target_sample_rate:
            audio = self.resample_audio(audio, sr, target_sample_rate)
            sr = target_sample_rate
        
        # Process audio (normalize, filter, etc.)
        audio = self.remove_dc_offset(audio)
        audio = self.normalize_audio(audio, method='peak', target_level=0.95)
        
        # Save in new format
        self.save_audio(audio, sr, output_path, format=output_format, 
                       bit_depth=bit_depth)
    
    def extract_audio_segment(self, input_path: str, output_path: str,
                            start_time: float, end_time: float,
                            fade_in: float = 0.01, fade_out: float = 0.01) -> None:
        """
        Extract a segment from audio file with optional fades.
        
        Args:
            input_path: Input audio file
            output_path: Output audio file
            start_time: Start time in seconds
            end_time: End time in seconds
            fade_in: Fade in duration in seconds
            fade_out: Fade out duration in seconds
        """
        duration = end_time - start_time
        audio, sr = self.load_audio_file(input_path, start_time=start_time, 
                                       duration=duration)
        
        # Apply fades
        if fade_in > 0:
            fade_samples = int(fade_in * sr)
            fade_curve = np.linspace(0, 1, fade_samples)
            audio[:fade_samples] *= fade_curve
            
        if fade_out > 0:
            fade_samples = int(fade_out * sr)
            fade_curve = np.linspace(1, 0, fade_samples)
            audio[-fade_samples:] *= fade_curve
        
        # Save segment
        self.save_audio(audio, sr, output_path)