import speech_recognition as sr
from pydub import AudioSegment
from pydub.silence import split_on_silence
from pydub.effects import normalize
import os
import re
import textwrap
import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext, messagebox
import threading
import subprocess
import platform

def format_transcription(text):
    """
    Format the transcribed text to improve readability:
    - Split into sentences
    - Create paragraphs based on longer pauses
    - Apply proper capitalization
    - Format text with proper line width
    """
    if not text:
        return ""
    
    # Ensure text is properly capitalized
    text = text.strip()
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    
    # Split text into sentences using punctuation marks
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    # Ensure first letter of each sentence is capitalized
    for i in range(len(sentences)):
        if sentences[i] and sentences[i][0].islower():
            sentences[i] = sentences[i][0].upper() + sentences[i][1:]
    
    # Rejoin sentences with proper spacing
    text = " ".join(sentences)
    
    # Wrap text to 80 characters max width for readability
    wrapped_text = textwrap.fill(text, width=80)
    
    # Add paragraph breaks for better readability (heuristic: approximately every 4-5 sentences)
    sentences = re.split(r'(?<=[.!?])\s+', wrapped_text)
    formatted_text = ""
    paragraph = ""
    
    for i, sentence in enumerate(sentences):
        paragraph += sentence + " "
        # Create a new paragraph after ~4-5 sentences or significant pause markers
        if (i + 1) % 4 == 0 or re.search(r'[.!?]\s*$', sentence):
            formatted_text += paragraph.strip() + "\n\n"
            paragraph = ""
    
    # Add any remaining text
    if paragraph:
        formatted_text += paragraph.strip()
    
    return formatted_text

def format_time(milliseconds):
    """Convert milliseconds to SRT time format (HH:MM:SS,mmm)"""
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def transcribe_mp3_to_text_and_srt(mp3_path, output_txt_path, output_srt_path, language='en-US', content_type='talk', update_callback=None):
    """
    Transcribe MP3 audio file to text and SRT subtitle file
    
    Parameters:
    - mp3_path: Path to the MP3 file
    - output_txt_path: Path for the output text file
    - output_srt_path: Path for the output SRT file
    - language: Language code (e.g., 'ar-SA' for Arabic, 'en-US' for English)
    - content_type: Type of audio content ('talk' or 'music')
    - update_callback: Function to call with status updates (for GUI)
    """
    try:
        if update_callback:
            update_callback(f"Processing MP3 file: {mp3_path}")
            update_callback(f"Selected language: {language}")
            update_callback(f"Content type: {content_type}")
        
        # Load the audio file
        if update_callback:
            update_callback("Loading audio file...")
        sound = AudioSegment.from_file(mp3_path, format="mp3")
        
        # Convert to mono and set appropriate sample rate for speech recognition
        sound = sound.set_channels(1)
        sound = sound.set_frame_rate(16000)
        
        # Normalize audio (adjust volume to a standard level)
        sound = normalize(sound)
        
        # Adjust parameters based on content type
        if content_type == 'music':
            # Music may have more varied volume levels and shorter pauses
            min_silence_len = 500  # Shorter silence detection for music with vocals
            silence_thresh = sound.dBFS - 14  # More sensitive threshold for music
            keep_silence = 500  # Keep shorter silence for music
        else:  # talk
            # Speech typically has more consistent pauses
            min_silence_len = 700  # Standard silence length for speech
            silence_thresh = sound.dBFS - 12  # Standard threshold for speech
            keep_silence = 700  # Keep standard silence for speech context
        
        # Split audio on silence to get chunks of speech
        if update_callback:
            update_callback(f"Splitting audio on silence (optimized for {content_type})...")
        chunks = split_on_silence(
            sound,
            min_silence_len=min_silence_len,
            silence_thresh=silence_thresh,
            keep_silence=keep_silence
        )
        
        # Create a directory to store the audio chunks
        temp_dir = "temp_audio_chunks"
        if not os.path.isdir(temp_dir):
            os.mkdir(temp_dir)
        
        # Create a speech recognizer
        recognizer = sr.Recognizer()
        
        # Adjust recognition parameters based on content type
        if content_type == 'music':
            # Music environment might have more background noise
            recognizer.energy_threshold = 350
            recognizer.dynamic_energy_threshold = True
            recognizer.dynamic_energy_adjustment_ratio = 1.5
        else:  # talk
            # Standard speech recognition settings
            recognizer.energy_threshold = 300
            recognizer.dynamic_energy_threshold = True
        
        # Process each chunk
        segment_texts = []  # Store individual segment texts for formatting
        subtitle_entries = []  # Store subtitle entries with timing info
        
        current_position = 0  # Track position in milliseconds
        
        if update_callback:
            update_callback(f"Processing {len(chunks)} audio segments...")
        
        for i, chunk in enumerate(chunks):
            # Calculate timing information
            start_time = current_position
            duration = len(chunk)
            end_time = start_time + duration
            current_position = end_time
            
            # Save chunk as a wav file
            chunk_filename = os.path.join(temp_dir, f"chunk{i}.wav")
            chunk.export(chunk_filename, format="wav")
            
            # Recognize speech in chunk
            with sr.AudioFile(chunk_filename) as source:
                audio = recognizer.record(source)
                try:
                    # Use the specified language
                    text = recognizer.recognize_google(audio, language=language)
                    if text:
                        segment_texts.append(text)
                        
                        # Add subtitle entry
                        subtitle_entries.append({
                            'index': i + 1,
                            'start': start_time,
                            'end': end_time,
                            'text': text
                        })
                        
                        if update_callback:
                            update_callback(f"Chunk {i+1}/{len(chunks)}: Transcribed successfully")
                except sr.UnknownValueError:
                    if update_callback:
                        update_callback(f"Chunk {i+1}/{len(chunks)}: Could not understand audio")
                except Exception as e:
                    if update_callback:
                        update_callback(f"Chunk {i+1}/{len(chunks)}: Error - {e}")
        
        # Combine all segments for text file
        if segment_texts:
            # Join the segments with proper spacing
            full_text = " ".join(segment_texts)
            
            # Format the text for better readability
            formatted_text = format_transcription(full_text)
            
            # Write formatted text to output file
            with open(output_txt_path, "w", encoding="utf-8") as file:
                file.write(formatted_text)
                
            # Generate SRT file
            with open(output_srt_path, "w", encoding="utf-8") as srt_file:
                for entry in subtitle_entries:
                    srt_file.write(f"{entry['index']}\n")
                    srt_file.write(f"{format_time(entry['start'])} --> {format_time(entry['end'])}\n")
                    srt_file.write(f"{entry['text']}\n\n")
            
            if update_callback:
                update_callback(f"SRT file saved to: {output_srt_path}")
                update_callback(f"Text file saved to: {output_txt_path}")
        else:
            with open(output_txt_path, "w", encoding="utf-8") as file:
                file.write("No speech detected in the audio file.")
            
            with open(output_srt_path, "w", encoding="utf-8") as srt_file:
                srt_file.write("1\n00:00:00,000 --> 00:00:01,000\nNo speech detected in the audio file.\n")
            
            if update_callback:
                update_callback("No speech detected in the audio file.")
        
        # Clean up
        for file in os.listdir(temp_dir):
            os.remove(os.path.join(temp_dir, file))
        os.rmdir(temp_dir)
        
        if update_callback:
            update_callback("Transcription complete!")
        return True
        
    except Exception as e:
        if update_callback:
            update_callback(f"Error during transcription: {e}")
        return False

class MP3TranscriberApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MP3 to Text & SRT Converter")
        self.root.geometry("800x600")
        self.root.minsize(700, 550)
        
        # Application info
        self.app_info = {
            "name": "MP3 to Text Converter with a GUI",
            "developer": "Ali Al-Kazaly \"aLi GeNiUs The Hackers\"",
            "version": "1.0.0.0"
        }
        
        # Language mapping (language name to code)
        self.languages = {
            "English (US)": "en-US",
            "English (UK)": "en-GB",
            "French": "fr-FR",
            "Spanish": "es-ES",
            "German": "de-DE",
            "Italian": "it-IT",
            "Portuguese": "pt-PT",
            "Russian": "ru-RU",
            "Japanese": "ja-JP",
            "Korean": "ko-KR",
            "Chinese (Mandarin)": "zh-CN",
            "Arabic": "ar-SA",
            "Hindi": "hi-IN",
            "Dutch": "nl-NL",
            "Swedish": "sv-SE",
            "Turkish": "tr-TR"
        }
        
        # Content types
        self.content_types = ["Talk/Speech", "Music with Lyrics"]
        
        # Set variables
        self.input_file_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.language_var = tk.StringVar(value="English (US)")  # Default language
        self.content_type_var = tk.StringVar(value="Talk/Speech")  # Default content type
        
        self.create_widgets()
    
    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Input section
        input_frame = ttk.LabelFrame(main_frame, text="Input Settings", padding="10")
        input_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # MP3 file selection
        ttk.Label(input_frame, text="MP3 File:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(input_frame, textvariable=self.input_file_var, width=50).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Button(input_frame, text="Browse...", command=self.browse_input_file).grid(row=0, column=2, padx=5, pady=5)
        
        # Output directory selection
        ttk.Label(input_frame, text="Output Directory:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(input_frame, textvariable=self.output_dir_var, width=50).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        ttk.Button(input_frame, text="Browse...", command=self.browse_output_dir).grid(row=1, column=2, padx=5, pady=5)
        
        # Language selection
        ttk.Label(input_frame, text="Language:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        language_combo = ttk.Combobox(input_frame, textvariable=self.language_var, values=list(self.languages.keys()), state="readonly")
        language_combo.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        # Content type selection
        ttk.Label(input_frame, text="Content Type:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        content_type_combo = ttk.Combobox(input_frame, textvariable=self.content_type_var, values=self.content_types, state="readonly")
        content_type_combo.grid(row=3, column=1, padx=5, pady=5, sticky=tk.W+tk.E)
        
        # Configure grid column weights
        input_frame.columnconfigure(1, weight=1)
        
        # Progress and log section
        log_frame = ttk.LabelFrame(main_frame, text="Progress Log", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Log area with scrollbar
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.config(state=tk.DISABLED)
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(log_frame, orient=tk.HORIZONTAL, length=100, mode='indeterminate', variable=self.progress_var)
        self.progress_bar.pack(fill=tk.X, padx=5, pady=5)
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=10)
        
        # Buttons
        ttk.Button(button_frame, text="Start Transcription", command=self.start_transcription).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Exit", command=self.root.quit).pack(side=tk.RIGHT, padx=5)
        
        # About Button - Added as requested
        ttk.Button(button_frame, text="About", command=self.show_about).pack(side=tk.LEFT, padx=5)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Add help tooltip for content type
        self.add_tooltip(content_type_combo, "Select 'Talk/Speech' for podcasts, interviews, or lectures. Select 'Music with Lyrics' for songs.")
    
    def show_about(self):
        """Display the About information dialog"""
        about_text = f"""
APP: {self.app_info['name']}
DEVELOPER: {self.app_info['developer']}
VERSION: {self.app_info['version']}
        """
        
        # Create custom about dialog
        about_dialog = tk.Toplevel(self.root)
        about_dialog.title("About")
        about_dialog.geometry("400x200")
        about_dialog.resizable(False, False)
        about_dialog.transient(self.root)  # Make dialog modal
        about_dialog.grab_set()
        
        # Make the dialog appear in center of parent window
        parent_x = self.root.winfo_x()
        parent_y = self.root.winfo_y()
        parent_width = self.root.winfo_width()
        parent_height = self.root.winfo_height()
        
        dialog_width = 400
        dialog_height = 200
        
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        
        about_dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        # Create frame for content
        content_frame = ttk.Frame(about_dialog, padding="20")
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # App name (large font)
        app_name_label = ttk.Label(content_frame, text=self.app_info['name'], font=("Arial", 14, "bold"))
        app_name_label.pack(pady=(0, 10))
        
        # Developer information
        dev_label = ttk.Label(content_frame, text=f"Developed by: {self.app_info['developer']}")
        dev_label.pack(pady=2)
        
        # Version information
        version_label = ttk.Label(content_frame, text=f"Version: {self.app_info['version']}")
        version_label.pack(pady=2)
        
        # Close button
        close_button = ttk.Button(content_frame, text="Close", command=about_dialog.destroy)
        close_button.pack(pady=(20, 0))
    
    def add_tooltip(self, widget, text):
        """Add a simple tooltip to a widget"""
        def show_tooltip(event):
            x, y, _, _ = widget.bbox("insert")
            x += widget.winfo_rootx() + 25
            y += widget.winfo_rooty() + 25
            
            # Create a toplevel window
            self.tooltip = tk.Toplevel(widget)
            self.tooltip.wm_overrideredirect(True)
            self.tooltip.wm_geometry(f"+{x}+{y}")
            
            label = ttk.Label(self.tooltip, text=text, justify=tk.LEFT,
                             background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                             wraplength=250)
            label.pack(padx=3, pady=3)
            
        def hide_tooltip(event):
            if hasattr(self, "tooltip"):
                self.tooltip.destroy()
                
        widget.bind("<Enter>", show_tooltip)
        widget.bind("<Leave>", hide_tooltip)
    
    def browse_input_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("MP3 Files", "*.mp3"), ("All Files", "*.*")]
        )
        if file_path:
            self.input_file_var.set(file_path)
            
            # Auto-set output directory to same as input file
            output_dir = os.path.dirname(file_path)
            self.output_dir_var.set(output_dir)
    
    def browse_output_dir(self):
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.output_dir_var.set(dir_path)
    
    def update_log(self, message):
        """Update the log text widget with a new message"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        # Update status bar
        self.status_var.set(message)
        
        # Force update of UI
        self.root.update_idletasks()
    
    def validate_inputs(self):
        """Validate user inputs before starting transcription"""
        input_file = self.input_file_var.get().strip()
        output_dir = self.output_dir_var.get().strip()
        
        if not input_file:
            messagebox.showerror("Error", "Please select an MP3 file.")
            return False
        
        if not os.path.exists(input_file):
            messagebox.showerror("Error", f"Input file '{input_file}' does not exist.")
            return False
        
        if not input_file.lower().endswith('.mp3'):
            messagebox.showerror("Error", "Input file must be an MP3 file.")
            return False
        
        if not output_dir:
            messagebox.showerror("Error", "Please select an output directory.")
            return False
        
        if not os.path.exists(output_dir):
            response = messagebox.askyesno("Directory Not Found", 
                                          f"Output directory '{output_dir}' does not exist. Create it?")
            if response:
                try:
                    os.makedirs(output_dir, exist_ok=True)
                    self.update_log(f"Created directory: {output_dir}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to create directory: {e}")
                    return False
            else:
                return False
        
        # Check write permissions on output directory
        if not os.access(output_dir, os.W_OK):
            messagebox.showerror("Error", f"No write permission for output directory: {output_dir}")
            return False
            
        return True
    
    def get_content_type_code(self):
        """Convert content type from display name to code"""
        content_type = self.content_type_var.get()
        if content_type == "Music with Lyrics":
            return "music"
        else:  # "Talk/Speech"
            return "talk"
    
    def start_transcription(self):
        """Start the transcription process"""
        if not self.validate_inputs():
            return
        
        # Get input values
        input_file = self.input_file_var.get()
        output_dir = self.output_dir_var.get()
        language_name = self.language_var.get()
        language_code = self.languages[language_name]
        content_type = self.get_content_type_code()
        
        # Determine output file paths
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        output_txt_path = os.path.join(output_dir, f"{base_name}.txt")
        output_srt_path = os.path.join(output_dir, f"{base_name}.srt")
        
        # Clear log and start progress bar
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.progress_bar.start()
        
        # Disable buttons during processing
        for widget in self.root.winfo_children():
            if isinstance(widget, ttk.Button):
                widget.config(state=tk.DISABLED)
        
        # Update log with initial info
        self.update_log("Starting transcription process...")
        self.update_log(f"Input file: {input_file}")
        self.update_log(f"Output directory: {output_dir}")
        self.update_log(f"Selected language: {language_name} ({language_code})")
        self.update_log(f"Content type: {content_type}")
        
        # Run transcription in a separate thread
        threading.Thread(
            target=self.run_transcription_thread,
            args=(input_file, output_txt_path, output_srt_path, language_code, content_type),
            daemon=True
        ).start()
    
    def run_transcription_thread(self, input_file, output_txt_path, output_srt_path, language_code, content_type):
        """Run the transcription in a separate thread to prevent UI freezing"""
        try:
            # Run transcription with callback for updates
            success = transcribe_mp3_to_text_and_srt(
                input_file, 
                output_txt_path, 
                output_srt_path, 
                language_code,
                content_type,
                self.update_log
            )
            
            # Update UI when complete
            self.root.after(0, lambda: self.transcription_complete(success, output_txt_path, output_srt_path))
            
        except Exception as e:
            self.root.after(0, lambda: self.update_log(f"Error: {str(e)}"))
            self.root.after(0, self.transcription_complete, False, None, None)
    
    def transcription_complete(self, success, txt_path, srt_path):
        """Handle completion of transcription process"""
        # Stop progress bar
        self.progress_bar.stop()
        
        # Re-enable buttons
        for widget in self.root.winfo_children():
            if isinstance(widget, ttk.Button):
                widget.config(state=tk.NORMAL)
        
        if success:
            self.update_log("Transcription completed successfully!")
            self.status_var.set("Ready - Transcription complete")
            
            # Ask if user wants to open the files
            if messagebox.askyesno("Transcription Complete", 
                                  "Transcription completed successfully. Would you like to open the output files?"):
                try:
                    # Open files in a cross-platform way
                    system = platform.system()
                    
                    if system == 'Windows':
                        # Windows
                        os.startfile(txt_path)
                        os.startfile(srt_path)
                    elif system == 'Darwin':
                        # macOS
                        subprocess.call(['open', txt_path])
                        subprocess.call(['open', srt_path])
                    else:
                        # Linux and other Unix-like systems
                        subprocess.call(['xdg-open', txt_path])
                        subprocess.call(['xdg-open', srt_path])
                        
                except Exception as e:
                    messagebox.showwarning("Warning", f"Could not open files: {e}")
                    self.update_log(f"Note: Files were saved successfully at {txt_path} and {srt_path}")
        else:
            self.update_log("Transcription failed. See log for details.")
            self.status_var.set("Ready - Transcription failed")
            messagebox.showerror("Error", "Transcription failed. See log for details.")

def main():
    root = tk.Tk()
    app = MP3TranscriberApp(root)
    
    # Set app icon (if available)
    try:
        root.iconbitmap("icon.ico")  # You can create and add an icon file
    except:
        pass
    
    # Apply theme if available
    try:
        # Try to use a more modern theme if available
        style = ttk.Style()
        available_themes = style.theme_names()
        if 'clam' in available_themes:
            style.theme_use('clam')
        elif 'vista' in available_themes:
            style.theme_use('vista')
    except:
        pass
    
    root.mainloop()

if __name__ == "__main__":
    main()
