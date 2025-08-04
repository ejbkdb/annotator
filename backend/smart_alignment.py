# backend/smart_alignment.py
import logging
import numpy as np
from scipy import signal
import matplotlib.pyplot as plt
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def find_best_offset(reference_audio: np.ndarray, target_audio: np.ndarray, sample_rate: int) -> tuple[int, float]:
    """
    Finds the best time offset of target_audio relative to reference_audio.

    Args:
        reference_audio: The reference audio signal as a NumPy array.
        target_audio: The target audio signal to align.
        sample_rate: The sample rate of the audio signals.

    Returns:
        A tuple containing:
        - offset_samples (int): The offset in samples. A positive value means
          the target event starts *after* the reference.
        - confidence (float): A confidence score from 0.0 to 1.0.
    """
    if reference_audio.size == 0 or target_audio.size == 0:
        return 0, 0.0

    # Normalize audio to have zero mean and unit variance
    ref_norm = (reference_audio - np.mean(reference_audio)) / (np.std(reference_audio) + 1e-9)
    target_norm = (target_audio - np.mean(target_audio)) / (np.std(target_audio) + 1e-9)
    
    # Calculate cross-correlation
    correlation = signal.correlate(target_norm, ref_norm, mode='full', method='fft')
    
    # The lag is the index of the max correlation value relative to the center
    lag_index = np.argmax(correlation)
    offset_samples = lag_index - (len(ref_norm) - 1)
    
    # Confidence is the normalized peak value of the correlation
    confidence = float(np.max(correlation) / np.sqrt(len(ref_norm) * len(target_norm)))
    confidence = max(0.0, min(1.0, confidence)) # Clamp to [0, 1]

    logging.info(f"Detected offset: {offset_samples} samples ({offset_samples / sample_rate:.3f}s) with confidence {confidence:.2f}")
    
    return int(offset_samples), confidence

def generate_verification_plot(
    reference_audio: np.ndarray,
    target_audio: np.ndarray,
    offset_samples: int,
    sample_rate: int,
    ref_name: str = "Reference",
    target_name: str = "Target",
    output_path: Path = None
):
    """
    Generates a plot showing the original and aligned waveforms for visual verification.
    """
    fig, axes = plt.subplots(3, 1, figsize=(15, 10), sharex=True)
    
    time_axis_ref = np.arange(len(reference_audio)) / sample_rate
    time_axis_target = np.arange(len(target_audio)) / sample_rate

    # 1. Plot Reference Audio
    axes[0].plot(time_axis_ref, reference_audio, label=ref_name, color='blue')
    axes[0].set_title(f"1. {ref_name} Signal")
    axes[0].legend()
    axes[0].grid(True, alpha=0.5)

    # 2. Plot Original Target Audio
    axes[1].plot(time_axis_target, target_audio, label=f"Original {target_name}", color='orangered')
    axes[1].set_title(f"2. Original {target_name} Signal")
    axes[1].legend()
    axes[1].grid(True, alpha=0.5)
    
    # 3. Plot Aligned Target Audio
    time_axis_aligned_target = (np.arange(len(target_audio)) - offset_samples) / sample_rate
    axes[2].plot(time_axis_ref, reference_audio, label=ref_name, color='blue', alpha=0.6)
    axes[2].plot(time_axis_aligned_target, target_audio, label=f"Aligned {target_name}", color='green')
    axes[2].set_title(f"3. Aligned Signals (Offset: {offset_samples/sample_rate:.3f}s)")
    axes[2].set_xlabel("Time (seconds)")
    axes[2].legend()
    axes[2].grid(True, alpha=0.5)

    plt.tight_layout()

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path)
        logging.info(f"Verification plot saved to {output_path}")
        plt.close(fig)
    else:
        plt.show()

def align_multi_sensor_event(
    event_audio: dict[str, np.ndarray],
    reference_sensor: str,
    sample_rate: int,
    plot_dir: Path = None
) -> tuple[dict[str, int], dict[str, float]]:
    """
    Aligns a multi-sensor event by finding offsets relative to a reference sensor.
    
    Args:
        event_audio: A dictionary mapping sensor names to audio data (np.ndarray).
        reference_sensor: The name of the sensor to use as the time reference.
        sample_rate: The sample rate of the audio.
        plot_dir: Optional directory to save verification plots.
    
    Returns:
        A tuple of (offsets, confidences) dictionaries.
    """
    if reference_sensor not in event_audio:
        raise ValueError(f"Reference sensor '{reference_sensor}' not found in event audio data.")

    ref_audio = event_audio[reference_sensor]
    offsets = {reference_sensor: 0}
    confidences = {reference_sensor: 1.0}

    for sensor_name, target_audio in event_audio.items():
        if sensor_name == reference_sensor:
            continue
        
        offset_samples, confidence = find_best_offset(ref_audio, target_audio, sample_rate)
        offsets[sensor_name] = offset_samples
        confidences[sensor_name] = confidence
        
        if plot_dir:
            plot_path = plot_dir / f"alignment_{reference_sensor}_vs_{sensor_name}.png"
            generate_verification_plot(
                ref_audio, target_audio, offset_samples, sample_rate, 
                ref_name=reference_sensor, target_name=sensor_name, output_path=plot_path
            )
            
    return offsets, confidences