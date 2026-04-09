# CloudStream Desktop

A Python + CustomTkinter desktop media center inspired by the CloudStream Android app.
Supports a plugin system compatible with CloudStream's architecture.

## Features

- **Home screen** — provider-powered content rows with horizontal scrolling
- **Search** — search across all installed providers with type/language filters
- **Content detail** — poster, plot, episodes, cast, recommendations
- **Video player** — python-mpv embedded player with seek, volume, subtitle selection
- **Downloads** — background download queue with progress tracking
- **Library** — bookmarks and watch history
- **Extensions** — add repositories, browse and install Python plugins
- **Sync** — AniList, MyAnimeList, Simkl tracking
- **Subtitles** — OpenSubtitles.com integration

## Requirements

- Python 3.10+
- pip packages: see `requirements.txt`
- **mpv** (optional, for embedded player): https://mpv.io/installation/

## Installation

```bash
# Clone or download
cd cloudstream-desktop

# Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

## Writing Plugins

See `assets/example_plugin/plugin.py` for a complete annotated example.

### Plugin structure

```
my_plugin/
├── manifest.json    # Plugin metadata
└── plugin.py        # Plugin code
```

### manifest.json

```json
{
  "name": "My Provider",
  "plugin_class_name": "MyPlugin",
  "version": 1,
  "internal_name": "my_provider",
  "description": "Provides content from mysite.com",
  "author": "Your Name",
  "language": "en",
  "tv_types": ["Movie", "TvSeries"]
}
```

### plugin.py — minimal example

```python
from plugins.base_plugin import BasePlugin
from core.main_api import MainAPI
from core.models import (
    TvType, MovieSearchResponse, MovieLoadResponse,
    ExtractorLink, MainPageData, HomePageResponse, HomePageList,
    MainPageRequest
)

class MyProvider(MainAPI):
    name = "My Provider"
    main_url = "https://mysite.com"
    lang = "en"
    supported_types = [TvType.Movie]
    has_main_page = True
    main_page = [MainPageData("Popular", "popular", False)]

    async def get_main_page(self, page, request):
        # Fetch and return HomePageResponse
        ...

    async def search(self, query):
        # Return list[SearchResponse]
        ...

    async def load(self, url):
        # Return LoadResponse
        ...

    async def load_links(self, data, is_casting, callback, subtitle_callback):
        # Call callback(ExtractorLink(...)) for each video link
        ...
        return True

class MyPlugin(BasePlugin):
    def load(self):
        self.register_main_api(MyProvider())
```

### Installing a local plugin

1. Copy your plugin folder to `~/Cloudstream3/plugins/` (Linux/macOS/Windows)
2. The app will auto-load it on startup
3. Or go to **Settings → Extensions** and use the file picker

### Adding a repository

Repositories use the same JSON format as CloudStream Android:

```json
{
  "pluginLists": [
    "https://raw.githubusercontent.com/yourname/myrepo/main/plugins.json"
  ]
}
```

Each `plugins.json` is a list of plugin metadata objects:

```json
[
  {
    "name": "My Provider",
    "internalName": "my_provider",
    "url": "https://raw.githubusercontent.com/yourname/myrepo/main/my_provider.py",
    "version": 1,
    "language": "en",
    "tvTypes": ["Movie"],
    "description": "..."
  }
]
```

## Project Structure

```
cloudstream-desktop/
├── core/               # Core API abstractions (MainAPI, ExtractorApi, models)
│   └── utils/          # HTTP helper, M3U8, subtitle utilities
├── plugins/            # Plugin loader and repository manager
├── ui/                 # CustomTkinter UI
│   ├── components/     # Reusable widgets (MediaCard, EpisodeList, etc.)
│   └── settings/       # Settings pages
├── sync/               # AniList, MAL, Simkl sync providers
├── subtitles/          # OpenSubtitles provider
├── data/               # SQLite database + preferences
├── assets/             # Static assets, example plugin
├── user_data/          # Plugin files (auto-managed)
├── main.py             # Entry point
└── requirements.txt
```

## Data Storage

All user data is stored in `~/.cloudstream-desktop/`:
- `cloudstream.db` — SQLite (watch history, bookmarks, downloads)
- `preferences.json` — settings
- `plugins/` — installed plugin files
- `repositories.json` — saved repositories

## License

This project is inspired by [CloudStream](https://github.com/recloudstream/cloudstream) (LGPL-3.0).
