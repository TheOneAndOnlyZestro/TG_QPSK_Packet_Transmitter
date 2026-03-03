import base64
def handle_jpg(data):
    filename = data.get('filename', 'received_image') + 'mina.jpg'
    payload = data.get('payload', '')
    
    try:
        img_bytes = base64.b64decode(payload)
        with open(filename, 'wb') as f:
            f.write(img_bytes)
        print(f"[SUCCESS] JPG image saved as: {filename}")
    except Exception as e:
        print(f"[ERROR] Failed to save JPG: {e}")

def handle_png(data):
    filename = data.get('filename', 'received_image.png')
    payload = data.get('payload', '')
    
    try:
        img_bytes = base64.b64decode(payload)
        with open(filename, 'wb') as f:
            f.write(img_bytes)
        print(f"[SUCCESS] PNG image saved as: {filename}")
    except Exception as e:
        print(f"[ERROR] Failed to save PNG: {e}")


extensions = {
    'jpg': handle_jpg,
    'jpeg': handle_jpg,
    'png': handle_png
}