from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, List, Callable
from core.models import (
    HomePageResponse, HomePageList, HomePageResponse,
    MainPageRequest, MainPageData, SearchResponse,
    SearchResponseList, LoadResponse, ExtractorLink,
    SubtitleFile, TvType
)


class MainAPI(ABC):
    """Abstract base class for all content providers. Equivalent to CloudStream's MainAPI."""

    name: str = "Unknown Provider"
    main_url: str = ""
    lang: str = "en"
    supported_types: List[TvType] = []
    has_main_page: bool = False
    has_quick_search: bool = False
    is_adult: bool = False
    source_plugin: Optional[str] = None

    # Main page data — list of (name, data_string, horizontal_images)
    main_page: List[MainPageData] = []

    async def get_main_page(
        self, page: int, request: MainPageRequest
    ) -> Optional[HomePageResponse]:
        """Return home page rows for the given request and page number."""
        raise NotImplementedError

    async def search(self, query: str) -> Optional[List[SearchResponse]]:
        """Return list of search results for the given query."""
        raise NotImplementedError

    async def search_paged(
        self, query: str, page: int
    ) -> Optional[SearchResponseList]:
        """Paginated search. Defaults to calling search() on page 1."""
        if page > 1:
            return None
        results = await self.search(query)
        if results is None:
            return None
        return SearchResponseList(items=results, has_next=False)

    async def quick_search(self, query: str) -> Optional[List[SearchResponse]]:
        """Fast autocomplete search. Defaults to search()."""
        return await self.search(query)

    async def load(self, url: str) -> Optional[LoadResponse]:
        """Load full content details from a URL (from search results)."""
        raise NotImplementedError

    async def load_links(
        self,
        data: str,
        is_casting: bool,
        callback: Callable[[ExtractorLink], None],
        subtitle_callback: Callable[[SubtitleFile], None],
    ) -> bool:
        """
        Extract playable links from episode data string.
        Call callback() for each ExtractorLink found.
        Call subtitle_callback() for each subtitle found.
        Returns True on success.
        """
        raise NotImplementedError

    async def get_load_url(self, sync_id_name: str, sync_id: str) -> Optional[str]:
        """Get a load() URL from an external sync ID (MAL, IMDB, etc.)."""
        return None

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name}>"
