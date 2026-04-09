from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Callable, Any


class TvType(str, Enum):
    Movie = "Movie"
    TvSeries = "TvSeries"
    Anime = "Anime"
    OVA = "OVA"
    AnimeMovie = "AnimeMovie"
    Cartoon = "Cartoon"
    Documentary = "Documentary"
    AsianDrama = "AsianDrama"
    Live = "Live"
    Torrent = "Torrent"
    Others = "Others"
    NSFW = "NSFW"


class SearchQuality(str, Enum):
    HD = "HD"
    FHD = "FHD"
    UHD_4K = "4K"
    SD = "SD"
    CAM = "CAM"
    HDR = "HDR"
    BlueRay = "BlueRay"
    Unknown = "Unknown"


class DubStatus(str, Enum):
    Dubbed = "Dubbed"
    Subbed = "Subbed"


class ExtractorLinkType(str, Enum):
    VIDEO = "VIDEO"
    M3U8 = "M3U8"
    DASH = "DASH"
    MAGNET = "MAGNET"
    TORRENT = "TORRENT"


class ShowStatus(str, Enum):
    Completed = "Completed"
    Ongoing = "Ongoing"
    Cancelled = "Cancelled"
    Hiatus = "Hiatus"


@dataclass
class SubtitleFile:
    lang: str
    url: str
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class ExtractorLink:
    source: str
    name: str
    url: str
    referer: str = ""
    quality: int = -1
    headers: Dict[str, str] = field(default_factory=dict)
    type: ExtractorLinkType = ExtractorLinkType.VIDEO
    is_m3u8: bool = False
    extract_data: Optional[str] = None

    def quality_str(self) -> str:
        if self.quality <= 0:
            return "Unknown"
        return f"{self.quality}p"


@dataclass
class TrailerData:
    extractor_url: str
    referer: str = ""
    raw: bool = False
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class Actor:
    name: str
    image: Optional[str] = None


@dataclass
class ActorData:
    actor: Actor
    role: Optional[str] = None
    role_string: Optional[str] = None
    voice_actor: Optional[Actor] = None


@dataclass
class SearchResponse:
    name: str
    url: str
    api_name: str
    type: Optional[TvType] = None
    poster_url: Optional[str] = None
    poster_headers: Optional[Dict[str, str]] = None
    year: Optional[int] = None
    quality: Optional[SearchQuality] = None
    id: Optional[int] = None

    def __hash__(self):
        return hash((self.url, self.api_name))


@dataclass
class MovieSearchResponse(SearchResponse):
    type: Optional[TvType] = TvType.Movie


@dataclass
class TvSeriesSearchResponse(SearchResponse):
    type: Optional[TvType] = TvType.TvSeries
    episodes: Optional[int] = None


@dataclass
class AnimeSearchResponse(SearchResponse):
    type: Optional[TvType] = TvType.Anime
    dub_status: Optional[DubStatus] = None
    dubbed_episodes: Optional[int] = None
    subbed_episodes: Optional[int] = None


@dataclass
class LiveSearchResponse(SearchResponse):
    type: Optional[TvType] = TvType.Live
    lang: Optional[str] = None


@dataclass
class Episode:
    data: str
    name: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    poster_url: Optional[str] = None
    description: Optional[str] = None
    date: Optional[int] = None
    run_time: Optional[int] = None

    def display_name(self) -> str:
        parts = []
        if self.season is not None:
            parts.append(f"S{self.season:02d}")
        if self.episode is not None:
            parts.append(f"E{self.episode:02d}")
        prefix = "".join(parts)
        if self.name:
            return f"{prefix} {self.name}".strip() if prefix else self.name
        return prefix or "Episode"


@dataclass
class SeasonData:
    season: int
    name: Optional[str] = None
    display_season: Optional[int] = None

    def display_name(self) -> str:
        num = self.display_season if self.display_season is not None else self.season
        return self.name or f"Season {num}"


@dataclass
class NextAiring:
    episode: int
    unix_time: int
    season: Optional[int] = None


@dataclass
class LoadResponse:
    name: str
    url: str
    api_name: str
    type: TvType
    poster_url: Optional[str] = None
    year: Optional[int] = None
    plot: Optional[str] = None
    score: Optional[float] = None
    tags: Optional[List[str]] = None
    duration: Optional[int] = None
    trailers: List[TrailerData] = field(default_factory=list)
    recommendations: Optional[List[SearchResponse]] = None
    actors: Optional[List[ActorData]] = None
    coming_soon: bool = False
    sync_data: Dict[str, str] = field(default_factory=dict)
    poster_headers: Optional[Dict[str, str]] = None
    background_poster_url: Optional[str] = None
    logo_url: Optional[str] = None
    content_rating: Optional[str] = None


@dataclass
class MovieLoadResponse(LoadResponse):
    type: TvType = TvType.Movie
    data_url: Optional[str] = None


@dataclass
class TvSeriesLoadResponse(LoadResponse):
    type: TvType = TvType.TvSeries
    episodes: List[Episode] = field(default_factory=list)
    season_names: Optional[List[SeasonData]] = None
    show_status: Optional[str] = None
    next_airing: Optional[NextAiring] = None


@dataclass
class AnimeLoadResponse(LoadResponse):
    type: TvType = TvType.Anime
    episodes: Dict[str, List[Episode]] = field(default_factory=dict)
    season_names: Optional[List[SeasonData]] = None
    show_status: Optional[str] = None
    next_airing: Optional[NextAiring] = None


@dataclass
class LiveStreamLoadResponse(LoadResponse):
    type: TvType = TvType.Live
    data_url: Optional[str] = None


@dataclass
class HomePageList:
    name: str
    list: List[SearchResponse] = field(default_factory=list)
    is_horizontal_images: bool = False


@dataclass
class HomePageResponse:
    items: List[HomePageList] = field(default_factory=list)
    has_next: bool = False


@dataclass
class MainPageRequest:
    name: str
    data: str
    horizontal_images: bool = False


@dataclass
class MainPageData:
    name: str
    data: str
    horizontal_images: bool = False


@dataclass
class SearchResponseList:
    items: List[SearchResponse] = field(default_factory=list)
    has_next: bool = False


@dataclass
class WatchHistoryEntry:
    url: str
    api_name: str
    name: str
    poster_url: Optional[str]
    episode: Optional[int]
    season: Optional[int]
    position: float  # seconds
    duration: float  # seconds
    timestamp: int   # unix
    episode_data: Optional[str] = None
    episode_name: Optional[str] = None


@dataclass
class BookmarkEntry:
    url: str
    api_name: str
    name: str
    type: TvType
    poster_url: Optional[str]
    timestamp: int


@dataclass
class DownloadEntry:
    id: str
    url: str
    title: str
    episode_name: Optional[str]
    file_path: str
    total_bytes: int
    downloaded_bytes: int
    status: str  # queued, downloading, paused, completed, failed
    timestamp: int
