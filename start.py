"""
start.py
Single command to start both the scraper and the web UI.
"""

import os
import sys
import json
import logging
import subprocess
import time
from pathlib import Path
from logging_config import setup_logging

logger = logging.getLogger(__name__)

PID_FILE = Path("pids.json")


def write_pids(pids: dict):
    """Write process PIDs to a JSON file for external stop commands."""
    PID_FILE.write_text(json.dumps(pids))


def clear_pids():
    """Remove PID file."""
    if PID_FILE.exists():
        PID_FILE.unlink()


def start_process(script_name: str, env: dict = None):
    """Start a Python script as a subprocess."""
    python = sys.executable
    cmd = [python, script_name]
    process = subprocess.Popen(
        cmd,
        cwd=Path(__file__).parent,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    logger.info(f"Started {script_name} (PID: {process.pid})")
    return process


def log_output(process: subprocess.Popen, prefix: str):
    """Log output from a subprocess."""
    for line in process.stdout:
        print(f"[{prefix}] {line.rstrip()}")


def main():
    """Start both scraper and web UI."""
    setup_logging()
    
    logger.info("Starting Novel Scraper")
    
    # Set environment to ensure child processes see current directory
    env = os.environ.copy()
    
    processes = []
    pids = {"start": os.getpid()}
    
    try:
        # Start web UI first
        logger.info("Starting web UI on http://localhost:6110")
        web_ui = start_process("web_ui.py", env)
        processes.append(("WEB-UI", web_ui))
        pids["web_ui"] = web_ui.pid
        
        # Give web UI a moment to initialize
        time.sleep(2)
        
        # Start scraper
        logger.info("Starting scraper")
        scraper = start_process("main.py", env)
        processes.append(("SCRAPER", scraper))
        pids["scraper"] = scraper.pid
        
        write_pids(pids)
        
        logger.info("All services started. Press Ctrl+C to stop.")
        
        # Log output from both processes
        import threading
        threads = []
        for prefix, process in processes:
            t = threading.Thread(target=log_output, args=(process, prefix), daemon=True)
            t.start()
            threads.append(t)
        
        # Wait for processes
        for _, process in processes:
            process.wait()
            
    except KeyboardInterrupt:
        logger.info("Stopping services...")
    finally:
        for name, process in processes:
            if process.poll() is None:
                logger.info(f"Terminating {name}")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        clear_pids()
        logger.info("All services stopped")


if __name__ == "__main__":
    main()
