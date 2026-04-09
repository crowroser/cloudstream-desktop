"""
Example CloudStream Desktop Plugin
===================================
This file demonstrates how to create a plugin for CloudStream Desktop.

To install this plugin:
  1. Copy this file and manifest.json to a folder
  2. In the app: Settings → Extensions → (drag and drop or copy to plugins folder)

Structure:
  - Subclass BasePlugin and implement load()
  - Create MainAPI providers for content sources
  - Create ExtractorApi extractors for video link resolution
"""

import sys
import os

# These imports will resolve at runtime inside the app
from plugins.base_plugin import BasePlugin
from core.main_api import MainAPI
from core.extractor_api import ExtractorApi
from core.models import (
    TvType, SearchResponse, MovieSearchResponse, TvSeriesSearchResponse,
    LoadResponse, MovieLoadResponse, TvSeriesLoadResponse,
    Episode, HomePageList, HomePageResponse, MainPageRequest, MainPageData,
    ExtractorLink, SubtitleFile, ExtractorLinkType,
)


# ---------------------------------------------------------------------------
# Example Provider — a fake/demo content source
# ---------------------------------------------------------------------------

class ExampleProvider(MainAPI):
    """
    Demo provider that returns hard-coded sample data.
    Replace with actual scraping logic for a real provider.
    """

    name = "Example Provider"
    main_url = "https://example.com"
    lang = "en"
    supported_types = [TvType.Movie, TvType.TvSeries]
    has_main_page = True

    # Define what sections appear on the home page
    main_page = [
        MainPageData(name="Popular Movies", data="movies/popular", horizontal_images=False),
        MainPageData(name="Trending Series", data="series/trending", horizontal_images=False),
    ]

    async def get_main_page(self, page: int, request: MainPageRequest):
        """Return sample home page rows."""
        items = []

        if request.data == "movies/popular":
            movies = [
                MovieSearchResponse(
                    name=f"Sample Movie {i}",
                    url=f"https://example.com/movie/{i}",
                    api_name=self.name,
                    poster_url=None,
                    year=2024 - i,
                )
                for i in range(1, 11)
            ]
            items.append(HomePageList(name=request.name, list=movies))

        elif request.data == "series/trending":
            series = [
                TvSeriesSearchResponse(
                    name=f"Sample Series {i}",
                    url=f"https://example.com/series/{i}",
                    api_name=self.name,
                    poster_url=None,
                    year=2023,
                    episodes=12,
                )
                for i in range(1, 9)
            ]
            items.append(HomePageList(name=request.name, list=series))

        return HomePageResponse(items=items, has_next=False)

    async def search(self, query: str):
        """Return fake search results matching the query."""
        results = []
        for i in range(1, 6):
            results.append(MovieSearchResponse(
                name=f"{query} — Result {i}",
                url=f"https://example.com/movie/search/{i}",
                api_name=self.name,
                year=2024,
            ))
        return results

    async def load(self, url: str):
        """Load full content details from a URL."""
        if "/movie/" in url:
            return MovieLoadResponse(
                name="Sample Movie",
                url=url,
                api_name=self.name,
                type=TvType.Movie,
                plot="This is a sample movie loaded by the Example Provider.",
                year=2024,
                score=7.5,
                tags=["Action", "Drama"],
                data_url=url + "/watch",
            )
        else:
            episodes = [
                Episode(
                    data=f"{url}/s1e{i}",
                    name=f"Episode {i}",
                    season=1,
                    episode=i,
                    description=f"This is episode {i} of the sample series.",
                )
                for i in range(1, 13)
            ]
            return TvSeriesLoadResponse(
                name="Sample Series",
                url=url,
                api_name=self.name,
                type=TvType.TvSeries,
                plot="This is a sample TV series.",
                year=2023,
                episodes=episodes,
            )

    async def load_links(self, data: str, is_casting: bool, callback, subtitle_callback):
        """
        Extract video links from episode/movie data.
        In a real plugin, scrape the page and find video embed URLs.
        Then call: callback(ExtractorLink(...))
        For subtitles: subtitle_callback(SubtitleFile(...))
        """
        # Example: return a direct test stream
        callback(ExtractorLink(
            source=self.name,
            name="1080p Stream",
            url="https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
            referer=self.main_url,
            quality=1080,
            type=ExtractorLinkType.VIDEO,
        ))
        callback(ExtractorLink(
            source=self.name,
            name="720p Stream",
            url="https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4",
            referer=self.main_url,
            quality=720,
            type=ExtractorLinkType.VIDEO,
        ))
        return True


# ---------------------------------------------------------------------------
# Example Extractor — resolves video embed URLs from a specific host
# ---------------------------------------------------------------------------

class ExampleExtractor(ExtractorApi):
    """
    Demo extractor for embed URLs from example-embed.com.
    In a real extractor you would fetch the embed page and parse video links.
    """

    name = "ExampleEmbed"
    main_url = "https://example-embed.com"
    requires_referer = True

    async def get_url(self, url: str, referer=None, subtitle_callback=None, callback=None):
        """
        Fetch embed page, extract video links, and pass them to callback.
        """
        # Pseudo-implementation (replace with actual scraping):
        from core.utils.http_helper import get_text
        from bs4 import BeautifulSoup

        try:
            html = await get_text(url, referer=referer)
            soup = BeautifulSoup(html, "lxml")
            # Find video source tags (site-specific)
            for source in soup.select("source[src]"):
                src = source.get("src")
                if src and callback:
                    callback(ExtractorLink(
                        source=self.name,
                        name="Stream",
                        url=src,
                        referer=url,
                        quality=720,
                    ))
        except Exception as e:
            print(f"[ExampleExtractor] Error: {e}")


# ---------------------------------------------------------------------------
# Plugin entry point
# ---------------------------------------------------------------------------

class ExamplePlugin(BasePlugin):
    """
    Plugin entry class — must match plugin_class_name in manifest.json.
    """

    def load(self):
        """Register all providers and extractors here."""
        self.register_main_api(ExampleProvider())
        self.register_extractor_api(ExampleExtractor())
        print(f"[ExamplePlugin] Loaded successfully!")

    def before_unload(self):
        """Clean up any resources (threads, connections, etc.)."""
        print(f"[ExamplePlugin] Unloaded.")
