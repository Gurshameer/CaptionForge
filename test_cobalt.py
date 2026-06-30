import requests

def test_cobalt():
    url = "https://www.youtube.com/shorts/LkaE6zxcZnU"
    try:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "CaptionForge/1.0"
        }
        data = {
            "url": url,
            "videoQuality": "720p"
        }
        resp = requests.post("https://api.cobalt.tools/api/json", json=data, headers=headers)
        print("Status:", resp.status_code)
        print("Text:", resp.text)
    except Exception as e:
        print("Failed!")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_cobalt()
