# YouTube Video Downloader

A simple web application built with **Flask** that lets you download YouTube videos through a clean browser interface.

<img width="1710" height="981" alt="Youtube" src="https://github.com/user-attachments/assets/456a73f2-e2f5-4f44-8bd6-21e6f036c31e" />


## Features

- Paste a YouTube link and download the video
- Choose the quality or format <!-- EDIT: keep only what your app really does -->
- Live download progress
- Simple and responsive UI

## Tech Stack

- **Backend:** Python, Flask
- **Frontend:** HTML, CSS, JavaScript
- **Downloader library:** yt-dlp <!-- EDIT: or pytube, whichever you use -->

## Requirements

Before you start, make sure you have these installed:

- [Python 3.9+](https://www.python.org/downloads/)
- [Git](https://git-scm.com/downloads)
- [ffmpeg](https://ffmpeg.org/download.html) (needed to merge video and audio) <!-- EDIT: remove if not used -->

## Installation and Setup

**1. Clone the repository**

```bash
git clone https://github.com/Nishit33/Youtube-video-downloader-flask.git
cd youtube-video-downloader-flask
```

**2. Create a virtual environment**

```bash
python3 -m venv venv
```

**3. Activate the virtual environment**

```bash
# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

**4. Install dependencies**

```bash
pip install -r requirements.txt
```

**5. Run the app**

```bash
python app.py
```

**6. Open in your browser**

```
http://127.0.0.1:5000
```

## Project Structure

```
youtube-video-downloader-flask/
├── app.py              # Flask backend
├── requirements.txt    # Python dependencies
├── screenshots/
│   └── home.png        # README screenshot
├── static/
│   ├── script.js       # Frontend logic
│   └── style.css       # Styling
└── templates/
    └── index.html      # Main page
```


## Disclaimer

This project is for **personal and educational purposes only**. Downloading videos may violate YouTube's Terms of Service. Only download content you own or have permission to download. The author is not responsible for any misuse.
