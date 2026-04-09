"""
Basit uluslararasılaştırma (i18n) modülü.
tr() fonksiyonu ile çeviri yapılır.
"""
from __future__ import annotations
from typing import Dict

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "tr": {
        # Navigasyon
        "Home": "Ana Sayfa",
        "Search": "Arama",
        "Library": "Kütüphane",
        "Downloads": "İndirmeler",
        "Settings": "Ayarlar",
        # Ana Sayfa
        "Loading content...": "İçerikler yükleniyor...",
        "No providers loaded.\nGo to Settings → Extensions to add plugins.": (
            "Sağlayıcı yüklenmedi.\nEklenti eklemek için Ayarlar → Uzantılar'a gidin."
        ),
        "No content available. Try adding more plugins.": (
            "İçerik bulunamadı. Daha fazla eklenti eklemeyi deneyin."
        ),
        "↻ Refresh": "↻ Yenile",
        "All Providers": "Tüm Sağlayıcılar",
        # Arama
        "Search movies, series, anime...": "Film, dizi, anime ara...",
        "Type something to search...": "Aramak için bir şey yazın...",
        'Searching for "{}..."': '"{}" aranıyor...',
        "No results found.": "Sonuç bulunamadı.",
        "No providers loaded. Add plugins first.": "Sağlayıcı yüklenmedi. Önce eklenti ekleyin.",
        "Type:": "Tür:",
        "Provider:": "Sağlayıcı:",
        "All Types": "Tüm Türler",
        "Movie": "Film",
        "TvSeries": "Dizi",
        "Anime": "Anime",
        "AsianDrama": "Asya Dizisi",
        "Cartoon": "Çizgi Film",
        "Documentary": "Belgesel",
        "Search": "Ara",
        # Kütüphane
        "Bookmarks": "Yer İmleri",
        "Watch History": "İzleme Geçmişi",
        "Continue Watching": "Kaldığım Yerden",
        "Library": "Kütüphane",
        "No bookmarks yet.\nBrowse content and tap ☆ to bookmark.": (
            "Henüz yer imi yok.\nİçeriklere göz atın ve ☆ ile yer imine ekleyin."
        ),
        "No watch history yet.": "Henüz izleme geçmişi yok.",
        "Nothing in progress.": "Devam eden içerik yok.",
        "Refresh": "Yenile",
        "Clear All": "Tümünü Temizle",
        # İndirmeler
        "Downloads": "İndirmeler",
        "Open Folder": "Klasörü Aç",
        "Active": "Aktif",
        "Completed": "Tamamlanan",
        "Failed": "Başarısız",
        "No active downloads.": "Aktif indirme yok.",
        "No completed downloads.": "Tamamlanan indirme yok.",
        "No failed downloads.": "Başarısız indirme yok.",
        "✕ Cancel": "✕ İptal",
        "▶ Open": "▶ Aç",
        "🗑 Delete": "🗑 Sil",
        "🗑 Remove": "🗑 Kaldır",
        "File not found.": "Dosya bulunamadı.",
        "Status: queued": "Durum: Kuyrukta",
        "Status: downloading": "Durum: İndiriliyor",
        "Status: completed": "Durum: Tamamlandı",
        "Status: failed": "Durum: Başarısız",
        "Status: cancelled": "Durum: İptal edildi",
        # Ayarlar
        "Settings": "Ayarlar",
        "General": "Genel",
        "Player": "Oynatıcı",
        "Sync": "Senkronizasyon",
        "Extensions": "Uzantılar",
        "About": "Hakkında",
        "Providers": "Sağlayıcılar",
        "Appearance": "Görünüm",
        "Theme": "Tema",
        "Accent Color": "Vurgu Rengi",
        "Language": "Dil",
        "Interface Language": "Arayüz Dili",
        "Playback": "Oynatma",
        "Remember playback position": "Oynatma konumunu hatırla",
        "Auto-play next episode": "Sonraki bölümü otomatik oynat",
        "Skip intro (AniSkip)": "Giriş atla (AniSkip)",
        "Subtitles": "Altyazılar",
        "Enable subtitles by default": "Altyazıları varsayılan olarak aç",
        "Default subtitle language": "Varsayılan altyazı dili",
        "Subtitle font size": "Altyazı yazı tipi boyutu",
        "Volume": "Ses",
        "Default volume": "Varsayılan ses seviyesi",
        "Download Location": "İndirme Konumu",
        "Browse": "Gözat",
        "Parallel Downloads": "Paralel İndirmeler",
        "Max simultaneous downloads": "Maks. eş zamanlı indirme",
        "Content Filters": "İçerik Filtreleri",
        "Show adult (18+) content": "Yetişkin (18+) içeriği göster",
        "Loaded Providers": "Yüklü Sağlayıcılar",
        "Connect": "Bağlan",
        "Disconnect": "Bağlantıyı Kes",
        "Connected ✓": "Bağlandı ✓",
        "Not connected": "Bağlanmadı",
        # Uzantılar
        "Repositories": "Depolar",
        "Repository URL (https://...)": "Depo URL'si (https:// veya cloudstreamrepo://...)",
        "Add Repo": "Depo Ekle",
        "No repositories added yet.": "Henüz depo eklenmedi.",
        "Plugins": "Eklentiler",
        "Search plugins...": "Eklenti ara...",
        "↻ Fetch": "↻ Getir",
        'Click "↻ Fetch" to load available plugins from repositories.': (
            '"↻ Getir" butonuna tıklayarak depolardan eklentileri yükleyin.'
        ),
        'No plugins installed.\nAdd a repository above and click "↻ Fetch".': (
            'Eklenti yüklü değil.\nYukarıya depo ekleyin ve "↻ Getir"e tıklayın.'
        ),
        "Installed Plugins": "Yüklü Eklentiler",
        "No plugins match the filter.": "Filtreyle eşleşen eklenti bulunamadı.",
        "Install": "Yükle",
        "Uninstall": "Kaldır",
        "↑ Update": "↑ Güncelle",
        "Fetching plugins from repositories...": "Depolardan eklentiler getiriliyor...",
        # Hakkında
        "Python-powered media center with plugin support": (
            "Eklenti desteğiyle Python tabanlı medya merkezi"
        ),
        "Inspired by CloudStream (Android) by recloudstream": (
            "recloudstream'in CloudStream (Android) uygulamasından ilham alınmıştır"
        ),
        # Durum çubuğu
        "Ready": "Hazır",
        "No plugins loaded": "Eklenti yüklenmedi",
        "Repository added": "Depo eklendi",
        "Repository already exists.": "Bu depo zaten mevcut.",
        "Repository removed.": "Depo kaldırıldı.",
        "Plugin uninstalled.": "Eklenti kaldırıldı.",
        "Enter your {} API token:": "{} API token'ını girin:",
        "Connect {}": "{} Bağlan",
    }
}

_current_lang: str = "en"


def set_language(lang: str) -> None:
    global _current_lang
    _current_lang = lang


def get_language() -> str:
    return _current_lang


def tr(text: str) -> str:
    """Geçerli dile göre metni çevirir. Çeviri yoksa orijinal metni döndürür."""
    if _current_lang == "en":
        return text
    return TRANSLATIONS.get(_current_lang, {}).get(text, text)
