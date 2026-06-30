from pytubefix import YouTube

def test_pytube():
    url = "https://www.youtube.com/shorts/LkaE6zxcZnU"
    try:
        yt = YouTube(url, use_po_token=True)
        print("Title:", yt.title)
        stream = yt.streams.get_audio_only()
        print("Got stream:", stream)
        stream.download(filename="test.mp4")
        print("Success!")
    except Exception as e:
        print("Failed!")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_pytube()
