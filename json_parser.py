from data_handling import extensions
import json

#reception queue
_received_blocks = {}

def file_chunk_handler(data_dict):
    # Extract tracking info
            block_id = data_dict.get('block_id')
            chunk_id = data_dict.get('chunk_id')
            total_chunks = data_dict.get('total_chunks')
            filename = data_dict.get('filename')
            payload = data_dict.get('payload')
            
            if not block_id:
                return

            # Note: Out of order handling wrapper
            if block_id not in _received_blocks:
                _received_blocks[block_id] = {
                    'filename': filename,
                    'total_chunks': total_chunks,
                    'chunks': {}
                }
                
            block_state = _received_blocks[block_id]
            
            # Record it (repeated identical chunk_ids overwrite effortlessly avoiding duplication logic)
            if chunk_id not in block_state['chunks']:
                block_state['chunks'][chunk_id] = payload
                current_count = len(block_state['chunks'])
                print(f"[ASSEMBLY] '{filename}' - Received chunk {chunk_id + 1}/{total_chunks} ({current_count}/{total_chunks} total)")
            
            # Check if assembly is complete
            if len(block_state['chunks']) == total_chunks:
                print(f"[ASSEMBLY] File '{filename}' complete! Rebuilding base64 string...")
                
                # Sort the dictionary items by chunk_id and concatenate
                sorted_chunks = sorted(block_state['chunks'].items(), key=lambda x: x[0])
                full_base64 = "".join([chunk_data for _, chunk_data in sorted_chunks])
                
                # Send to final processing
                finalize_file({
                    'type': 'file',
                    'filename': block_state['filename'],
                    'payload': full_base64
                })
                
                # Cleanup the hash dictionary
                del _received_blocks[block_id]

def text_handler(data_dict):
    print(f"MESSAGE: {data_dict.get('payload')}")     

packet_types = {
    "file_chunk": file_chunk_handler,
    "text": text_handler
}
def finalize_file(data_dict):
    """Handles dispatching of fully assembled file files"""
    filename = data_dict.get('filename', '')
    if filename and '.' in filename:
        ext = filename.split('.')[-1].lower()
        if ext in extensions:
            extensions[ext](data_dict)
        else:
            print(f"[WARNING] No handler found for extension: .{ext}")
    else:
        print("[ERROR] File assembled but filename is missing or invalid.")

def process_json(extracted):
    print(f"RAW DATA: {extracted}")
    try:
        data_dict = json.loads(extracted)
        kind = data_dict.get('type')
        
        packet_types[kind](data_dict)
        
    except json.JSONDecodeError:
        print("[ERROR] Failed to parse JSON. Radio interference likely corrupted the packet.")
