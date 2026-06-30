import yt_dlp
import traceback

def test_yt():
    ydl_opts = {
        'format': 'best',
        'noplaylist': True,
        'quiet': False,
        'no_warnings': True,
        'legacyserverconnect': True,
        'nocheckcertificate': True,
    }
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("Extracting info...")
            info = ydl.extract_info(url, download=False)
            print("Success:", info.get('title'))
    except Exception as e:
        print("Failed!")
        traceback.print_exc()

if __name__ == "__main__":
    test_yt()
