"""
CleanVid GUI - Advanced Pipeline Control

Features:
- Batch Mode: Folder scan or .txt list
- Manual Mode: Single video with autopopulate
- Pipeline Control Panel: Force/Skip checkboxes for each step
- Pre-run confirmation summary
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import subprocess
import os
import sys
from pathlib import Path
import threading

# Add root to sys.path
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

from scripts.pipeline import Pipeline, PipelineContext, StepStatus, create_pipeline_for_video
import Global_Config
import utilization


class CleanVidGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("CleanVid Pipeline")
        self.root.geometry("800x700")
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.pipeline = None
        self.step_vars = {}  # {step_num: {'force': BooleanVar, 'skip': BooleanVar}}
        
        self.create_widgets()
        
    def create_widgets(self):
        # Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="x", padx=10, pady=5)
        
        self.batch_frame = ttk.Frame(self.notebook)
        self.manual_frame = ttk.Frame(self.notebook)
        
        self.notebook.add(self.batch_frame, text="Batch Mode")
        self.notebook.add(self.manual_frame, text="Manual Mode")
        
        self.setup_batch_tab()
        self.setup_manual_tab()
        
        # Pipeline Control Panel (shared, below tabs)
        self.setup_pipeline_panel()
        
        # Log Output
        log_frame = ttk.LabelFrame(self.root, text="Log Output", padding=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.log_text = tk.Text(log_frame, height=10, state="disabled")
        self.log_text.pack(fill="both", expand=True)

    def setup_batch_tab(self):
        input_frame = ttk.LabelFrame(self.batch_frame, text="Input", padding=10)
        input_frame.pack(fill="x", padx=10, pady=10)
        
        self.batch_mode_var = tk.StringVar(value="folder")
        
        ttk.Radiobutton(input_frame, text="Folder", variable=self.batch_mode_var, value="folder").grid(row=0, column=0, sticky="w")
        self.batch_folder_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.batch_folder_var).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(input_frame, text="Browse", command=lambda: self.browse_dir(self.batch_folder_var)).grid(row=0, column=2)
        
        ttk.Radiobutton(input_frame, text=".txt List", variable=self.batch_mode_var, value="list").grid(row=1, column=0, sticky="w", pady=5)
        self.batch_list_var = tk.StringVar(value=str(Global_Config.DEFAULT_BATCH_FILE))
        ttk.Entry(input_frame, textvariable=self.batch_list_var).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Button(input_frame, text="Browse", command=lambda: self.browse_file(self.batch_list_var, [("Text", "*.txt")])).grid(row=1, column=2)
        
        input_frame.columnconfigure(1, weight=1)
        
        # Utilization Status
        util_frame = ttk.LabelFrame(self.batch_frame, text="Credit Usage", padding=5)
        util_frame.pack(fill="x", padx=10, pady=5)
        self.util_label = ttk.Label(util_frame, text=utilization.get_usage_summary())
        self.util_label.pack(anchor="w")
        ttk.Button(util_frame, text="Refresh", command=self.refresh_utilization).pack(anchor="e")
        
    def setup_manual_tab(self):
        # Video File
        vid_frame = ttk.LabelFrame(self.manual_frame, text="Video File", padding=10)
        vid_frame.pack(fill="x", padx=10, pady=5)
        
        self.man_video_var = tk.StringVar()
        ttk.Entry(vid_frame, textvariable=self.man_video_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(vid_frame, text="Browse", command=self.browse_manual_video).pack(side="left")
        ttk.Button(vid_frame, text="Analyze", command=self.analyze_video).pack(side="left", padx=5)
        
        # Related Files (autopopulated, editable)
        rel_frame = ttk.LabelFrame(self.manual_frame, text="Discovered Files (Editable)", padding=10)
        rel_frame.pack(fill="x", padx=10, pady=5)
        
        labels = ["Audio:", "Response:", "Subtitle:", "CSV:", "Mute List:", "Clean Video:"]
        self.path_vars = {}
        for i, label in enumerate(labels):
            key = label.replace(":", "").lower().replace(" ", "_")
            ttk.Label(rel_frame, text=label).grid(row=i, column=0, sticky="w")
            var = tk.StringVar()
            self.path_vars[key] = var
            ttk.Entry(rel_frame, textvariable=var).grid(row=i, column=1, sticky="ew", padx=5, pady=1)
            ttk.Button(rel_frame, text="...", width=3, command=lambda v=var: self.browse_any(v)).grid(row=i, column=2)
        
        rel_frame.columnconfigure(1, weight=1)
        
    def setup_pipeline_panel(self):
        panel_frame = ttk.LabelFrame(self.root, text="Pipeline Steps", padding=10)
        panel_frame.pack(fill="x", padx=10, pady=5)
        
        # Header
        ttk.Label(panel_frame, text="Step", font=("", 9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(panel_frame, text="Name", font=("", 9, "bold")).grid(row=0, column=1, sticky="w", padx=10)
        ttk.Label(panel_frame, text="Status", font=("", 9, "bold")).grid(row=0, column=2, sticky="w", padx=10)
        ttk.Label(panel_frame, text="Force", font=("", 9, "bold")).grid(row=0, column=3)
        ttk.Label(panel_frame, text="Skip", font=("", 9, "bold")).grid(row=0, column=4)
        
        self.step_labels = {}
        step_names = [
            "Extract Audio",
            "Upload Audio",
            "Transcribe",
            "Merge Subtitles",
            "Generate Mute List",
            "Apply Mute List"
        ]
        
        for i, name in enumerate(step_names, start=1):
            row = i
            ttk.Label(panel_frame, text=str(i)).grid(row=row, column=0, sticky="w")
            ttk.Label(panel_frame, text=name).grid(row=row, column=1, sticky="w", padx=10)
            
            status_label = ttk.Label(panel_frame, text="○ Pending")
            status_label.grid(row=row, column=2, sticky="w", padx=10)
            self.step_labels[i] = status_label
            
            force_var = tk.BooleanVar(value=False)
            skip_var = tk.BooleanVar(value=(i == 4))  # Step 4 skipped by default
            
            ttk.Checkbutton(panel_frame, variable=force_var, command=lambda n=i: self.on_force_change(n)).grid(row=row, column=3)
            ttk.Checkbutton(panel_frame, variable=skip_var, command=lambda n=i: self.on_skip_change(n)).grid(row=row, column=4)
            
            self.step_vars[i] = {'force': force_var, 'skip': skip_var}
        
        # Run Button
        btn_frame = ttk.Frame(self.root, padding=5)
        btn_frame.pack(fill="x", padx=10)
        
        ttk.Button(btn_frame, text="Preview Run", command=self.preview_run).pack(side="left", padx=5)
        self.run_btn = ttk.Button(btn_frame, text="▶ Run Pipeline", command=self.run_pipeline)
        self.run_btn.pack(side="left", padx=5)
        
    # --- Actions ---
    
    def browse_dir(self, var):
        d = filedialog.askdirectory()
        if d: var.set(d)
        
    def browse_file(self, var, types):
        f = filedialog.askopenfilename(filetypes=types)
        if f: var.set(f)
        
    def browse_any(self, var):
        f = filedialog.askopenfilename()
        if f: var.set(f)
        
    def browse_manual_video(self):
        f = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mkv *.avi *.mov")])
        if f:
            self.man_video_var.set(f)
            self.analyze_video()
            
    def refresh_utilization(self):
        self.util_label.config(text=utilization.get_usage_summary())
            
    def analyze_video(self):
        """Create pipeline and populate fields."""
        vid = self.man_video_var.get()
        if not vid or not os.path.exists(vid):
            messagebox.showerror("Error", "Select a valid video file first.")
            return
            
        # Check for access permissions (e.g. file locked/permission denied)
        try:
            with open(vid, 'rb') as f:
                pass
        except OSError as e:
            messagebox.showerror("Error", f"Cannot access video file (Permission Denied?):\n{e}")
            return
            
        self.pipeline = create_pipeline_for_video(Path(vid))
        ctx = self.pipeline.context
        
        # Populate path vars
        self.path_vars["audio"].set(str(ctx.audio_path or ""))
        self.path_vars["response"].set(str(ctx.response_path or ""))
        self.path_vars["subtitle"].set(str(ctx.subtitle_path or ""))
        self.path_vars["csv"].set(str(ctx.csv_path or ""))
        self.path_vars["mute_list"].set(str(ctx.mute_list_path or ""))
        self.path_vars["clean_video"].set(str(ctx.clean_video_path or ""))
        
        # Update status labels
        for step in self.pipeline.steps:
            label = self.step_labels.get(step.number)
            if label:
                if step.status == StepStatus.DONE:
                    label.config(text="✓ Done", foreground="green")
                else:
                    label.config(text="○ Pending", foreground="black")
                    
        # Show warnings
        if ctx.audio_track_warning:
            messagebox.showwarning("Audio Track Warning", ctx.audio_track_warning)
            
        if ctx.subtitle_match_confidence < 0.7 and ctx.subtitle_path:
            messagebox.showwarning(
                "Low Subtitle Match",
                f"Subtitle match confidence: {ctx.subtitle_match_confidence:.0%}\n"
                f"File: {ctx.subtitle_path.name}\n\n"
                "Please verify this is the correct subtitle file."
            )
            
        self.log(f"Analyzed: {Path(vid).name}")
        
    def on_force_change(self, step_num):
        """When force is checked, cascade to later steps."""
        if self.step_vars[step_num]['force'].get():
            self.step_vars[step_num]['skip'].set(False)
            for i in range(step_num + 1, 7):  # Start from step_num + 1
                if i in self.step_vars:
                    self.step_vars[i]['force'].set(True)  # Also force later steps
                    self.step_vars[i]['skip'].set(False)

    def on_skip_change(self, step_num):
        """When skip is checked, uncheck force."""
        if self.step_vars[step_num]['skip'].get():
            self.step_vars[step_num]['force'].set(False)
                    
    def preview_run(self):
        """Show what will happen before running."""
        if not self.pipeline:
            self.analyze_video()
            if not self.pipeline:
                return
                
        # Apply force/skip from GUI to pipeline
        for i, vars in self.step_vars.items():
            step = self.pipeline.steps[i-1]
            step.force = vars['force'].get()
            step.skip = vars['skip'].get()
            
        summary = self.pipeline.get_summary()
        
        msg = "=== Pipeline Preview ===\n\n"
        
        if summary['will_run']:
            msg += "WILL RUN:\n"
            for num, name in summary['will_run']:
                msg += f"  • Step {num}: {name}\n"
        else:
            msg += "NOTHING TO RUN (all done or skipped)\n"
            
        if summary['already_done']:
            msg += "\nALREADY DONE (will skip):\n"
            for num, name in summary['already_done']:
                msg += f"  • Step {num}: {name}\n"
                
        if summary['will_skip']:
            msg += "\nEXPLICITLY SKIPPED:\n"
            for num, name in summary['will_skip']:
                msg += f"  • Step {num}: {name}\n"
                
        if summary['warnings']:
            msg += "\n⚠ WARNINGS:\n"
            for w in summary['warnings']:
                msg += f"  {w}\n"
                
        messagebox.showinfo("Pipeline Preview", msg)
        
    def reset_app(self):
        """Restart the application completely."""
        self.root.destroy()
        # Restart the current process
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def run_pipeline(self):
        if not self.pipeline:
            self.analyze_video()
            if not self.pipeline:
                return
                
        # Apply force/skip from GUI
        for i, vars in self.step_vars.items():
            step = self.pipeline.steps[i-1]
            step.force = vars['force'].get()
            step.skip = vars['skip'].get()
            
        # Pre-flight check: Ensure file is still accessible
        vid_path = self.pipeline.context.video_path
        if vid_path and vid_path.exists():
            try:
                with open(vid_path, 'rb'):
                    pass
            except OSError as e:
                messagebox.showerror("Error", f"Cannot access video file (Permission Denied?):\n{e}")
                return
            
        # Confirm
        summary = self.pipeline.get_summary()
        if not summary['will_run']:
            messagebox.showinfo("Nothing to do", "All steps are already done or skipped.")
            return
            
        steps_str = ", ".join([f"{num}" for num, _ in summary['will_run']])
        if not messagebox.askyesno("Confirm", f"Run steps: {steps_str}?"):
            return
            
        # Reset any previous error states in the pipeline object
        self.pipeline.detect_status()
        
        # Update GUI to remove old error/skipped labels immediately
        for step in self.pipeline.steps:
            self.update_step_status(step)
            
        self.run_btn.config(state="disabled")
        
        def run_thread():
            def callback(step):
                self.root.after(0, lambda: self.update_step_status(step))
                
            self.pipeline.run(callback=callback)
            
            # Check for errors
            errors = [s for s in self.pipeline.steps if s.status == StepStatus.ERROR]
            
            self.root.after(0, lambda: self.run_btn.config(state="normal"))
            if errors:
                err_msg = f"Pipeline failed at Step {errors[0].number}: {errors[0].name}\n\n{errors[0].error_message}"
                self.root.after(0, lambda: self.log(f"ERROR: {err_msg}"))
                self.root.after(0, lambda: messagebox.showerror("Error", err_msg))
            else:
                self.root.after(0, lambda: messagebox.showinfo("Done", "Pipeline completed successfully."))
            
        thread = threading.Thread(target=run_thread)
        thread.start()
        
    def update_step_status(self, step):
        label = self.step_labels.get(step.number)
        if label:
            if step.status == StepStatus.RUNNING:
                label.config(text="⟳ Running...", foreground="blue")
            elif step.status == StepStatus.DONE:
                label.config(text="✓ Done", foreground="green")
            elif step.status == StepStatus.ERROR:
                label.config(text="✗ Error", foreground="red")
            elif step.status == StepStatus.SKIPPED:
                label.config(text="⊘ Skipped", foreground="gray")
            elif step.status == StepStatus.PENDING:
                label.config(text="○ Pending", foreground="black")
                
        self.log(f"Step {step.number} ({step.name}): {step.status.value}")
        if step.error_message:
            self.log(f"  → {step.error_message}")
        
    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    app = CleanVidGUI(root)
    
    # Add Reload Button to top right (hacky but works)
    reload_btn = ttk.Button(root, text="⟳ Reload App", command=app.reset_app, width=12)
    reload_btn.place(relx=1.0, x=-10, y=5, anchor="ne")
    
    root.mainloop()
