import os
import re

dump_file = "aradhyaspace11-polluxpenguin-beta-8a5edab282632443.txt"
output_dir = "."

def extract_files():
    if not os.path.exists(dump_file):
        print(f"Error: {dump_file} not found.")
        return

    with open(dump_file, 'r') as f:
        content = f.read()

    # Split by the file separator
    sections = re.split(r'={20,}\nFILE: ', content)
    
    # The first section is the directory structure info, skip or log it
    print("Extracting files...")
    
    for section in sections[1:]:
        match = re.search(r'^(.*?)\n={20,}\n(.*)', section, re.DOTALL)
        if match:
            filepath = match.group(1).strip()
            file_content = match.group(2).strip()
            
            # Remove line numbers from content if they were added in the dump
            # The dump format is "1: Content"
            cleaned_content = []
            for line in file_content.split('\n'):
                # Handle cases where line might be "1: " or empty
                line_match = re.match(r'^\d+:\s?(.*)', line)
                if line_match:
                    cleaned_content.append(line_match.group(1))
                else:
                    cleaned_content.append(line)
            
            full_path = os.path.join(output_dir, filepath)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            with open(full_path, 'w') as out_f:
                out_f.write('\n'.join(cleaned_content))
            print(f"Extracted: {filepath}")

    print("Extraction complete.")

if __name__ == "__main__":
    extract_files()
