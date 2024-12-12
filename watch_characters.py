#!/usr/bin/env python3
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time
import json
import os
from threading import Timer

class CharacterDirectoryHandler(FileSystemEventHandler):
    def __init__(self):
        self.characters_dir = 'characters'
        if not os.path.exists(self.characters_dir):
            os.makedirs(self.characters_dir)
            print(f"Created characters directory: {self.characters_dir}")
        
        self.update_index()  # Initial update
    
    def on_any_event(self, event):
        if event.is_directory or 'index.json' in event.src_path:
            return
            
        print(f"Change detected in: {event.src_path}")
        # Small delay to ensure file writing is complete
        time.sleep(0.1)
        self.update_index()
    
    def update_index(self):
        try:
            character_files = [f for f in os.listdir(self.characters_dir) 
                             if f.endswith('.json') and f != 'index.json']
            
            print(f"Found character files: {character_files}")
            
            valid_files = []
            for file in character_files:
                try:
                    file_path = os.path.join(self.characters_dir, file)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        json.load(f)
                    valid_files.append(file)
                except Exception as e:
                    print(f"Warning: Invalid file {file}: {str(e)}")
            
            index_data = {
                "characters": sorted(valid_files),
                "lastUpdated": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            index_path = os.path.join(self.characters_dir, 'index.json')
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=4)
            
            print(f"Updated index.json - {len(valid_files)} valid characters found")
            
        except Exception as e:
            print(f"Error updating index: {str(e)}")

def main():
    event_handler = CharacterDirectoryHandler()
    observer = Observer()
    observer.schedule(event_handler, path='characters', recursive=False)
    observer.start()
    
    print("Watching characters directory for changes...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\nStopping watch...")
        observer.join()

if __name__ == "__main__":
    main()