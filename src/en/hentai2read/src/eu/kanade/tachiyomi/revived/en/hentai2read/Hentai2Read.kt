package eu.kanade.tachiyomi.revived.en.hentai2read

import eu.kanade.tachiyomi.network.GET
import eu.kanade.tachiyomi.network.asObservableSuccess
import eu.kanade.tachiyomi.source.model.FilterList
import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import eu.kanade.tachiyomi.source.online.ParsedHttpSource
import eu.kanade.tachiyomi.util.asJsoup
import java.text.SimpleDateFormat
import java.util.Locale
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.jsoup.nodes.Document
import org.jsoup.nodes.Element
import rx.Observable

class Hentai2Read : ParsedHttpSource() {

    override val name = "Hentai2Read"

    override val baseUrl = "https://hentai2read.com"

    override val lang = "en"

    override val supportsLatest = true

    override val client: OkHttpClient = network.cloudflareClient

    private val json = Json { ignoreUnknownKeys = true }

    companion object {
        const val PREFIX_ID_SEARCH = "id:"
    }

    // Popular

    override fun popularMangaRequest(page: Int) =
        GET("$baseUrl/browse/most-viewed${pageSuffix(page)}", headers)

    override fun popularMangaParse(response: Response) = parseBookList(response.asJsoup())

    override fun popularMangaSelector() = ""

    override fun popularMangaNextPageSelector(): String? = null

    override fun popularMangaFromElement(element: Element): SManga =
        throw UnsupportedOperationException("Not used")

    // Latest

    override fun latestUpdatesRequest(page: Int) =
        GET("$baseUrl/browse/newest${pageSuffix(page)}", headers)

    override fun latestUpdatesParse(response: Response) = parseBookList(response.asJsoup())

    override fun latestUpdatesSelector() = ""

    override fun latestUpdatesNextPageSelector(): String? = null

    override fun latestUpdatesFromElement(element: Element): SManga =
        throw UnsupportedOperationException("Not used")

    // Search

    override fun searchMangaRequest(page: Int, query: String, filters: FilterList): Request {
        val url = "$baseUrl/search".toHttpUrlOrNull()!!.newBuilder()
            .addQueryParameter("q", query)
            .apply {
                if (page > 1) {
                    addQueryParameter("page", page.toString())
                }
            }
            .build()
        return GET(url.toString(), headers)
    }

    override fun fetchSearchManga(page: Int, query: String, filters: FilterList): Observable<MangasPage> {
        val id = query.removePrefix(PREFIX_ID_SEARCH).trim()
        return if (query.startsWith(PREFIX_ID_SEARCH) && id.isNotEmpty()) {
            client.newCall(GET("$baseUrl/doujinshi/$id", headers)).asObservableSuccess()
                .map { response ->
                    MangasPage(listOf(mangaDetailsParse(response.asJsoup())), false)
                }
        } else {
            super.fetchSearchManga(page, query, filters)
        }
    }

    override fun searchMangaParse(response: Response) = parseBookList(response.asJsoup())

    override fun searchMangaSelector() = ""

    override fun searchMangaNextPageSelector(): String? = null

    override fun searchMangaFromElement(element: Element): SManga =
        throw UnsupportedOperationException("Not used")

    // Details

    override fun mangaDetailsParse(document: Document): SManga {
        val props = document.pageProps()
        val book = props["book"]!!.jsonObject
        val groups = props["groups"]?.jsonArray ?: JsonArray(emptyList())
        val groupMap = groups.associate { group ->
            val groupObject = group.jsonObject
            val label = groupObject.stringOrNull("label").orEmpty()
            val tags = groupObject["tags"]?.jsonArray
                ?.mapNotNull { it.jsonObject.stringOrNull("name") }
                ?: emptyList()

            label to tags
        }
        val tags = book["tags"]?.jsonArray
            ?.mapNotNull { it.jsonObject.stringOrNull("name") }
            ?: emptyList()
        val artists = groupMap["Artist"].orEmpty()

        return SManga.create().apply {
            title = book.stringOrNull("title").orEmpty()
            setUrlWithoutDomain(book.stringOrNull("url").orEmpty())
            thumbnail_url = book.stringOrNull("cover")
            author = artists.joinToString()
            artist = author
            genre = tags.joinToString()
            status = when (book["status"]?.jsonObject?.stringOrNull("label")) {
                "Ongoing" -> SManga.ONGOING
                "Completed" -> SManga.COMPLETED
                else -> SManga.UNKNOWN
            }
            description = groupMap
                .filterValues { it.isNotEmpty() }
                .map { (label, values) -> "$label:\n${values.joinToString()}" }
                .joinToString("\n\n")
        }
    }

    // Chapters

    override fun chapterListParse(response: Response): List<SChapter> {
        val props = response.asJsoup().pageProps()
        return props["chapters"]?.jsonArray?.map { it.jsonObject.toChapter() } ?: emptyList()
    }

    override fun chapterListSelector() = ""

    override fun chapterFromElement(element: Element): SChapter =
        throw UnsupportedOperationException("Not used")

    // Pages

    override fun pageListParse(response: Response): List<Page> {
        val props = response.asJsoup().pageProps()
        return props["images"]?.jsonArray?.mapIndexed { index, image ->
            Page(index, imageUrl = image.jsonPrimitive.content)
        } ?: emptyList()
    }

    override fun pageListParse(document: Document): List<Page> =
        throw UnsupportedOperationException("Not used")

    override fun imageUrlParse(document: Document) =
        throw UnsupportedOperationException("Not used")

    // Filters

    override fun getFilterList() = FilterList()

    // Helpers

    private fun pageSuffix(page: Int) = if (page > 1) "/page-$page" else ""

    private fun parseBookList(document: Document): MangasPage {
        val books = document.pageProps()["books"]?.jsonObject
            ?: return MangasPage(emptyList(), false)
        val data = books["data"]?.jsonArray ?: JsonArray(emptyList())
        val page = books["page"]?.jsonPrimitive?.intOrNull ?: 1
        val lastPage = books["lastPage"]?.jsonPrimitive?.intOrNull ?: page

        return MangasPage(data.map { it.jsonObject.toSManga() }, page < lastPage)
    }

    private fun Document.pageProps(): JsonObject {
        val data = selectFirst("script[data-page=app]")?.data()
            ?: throw Exception("Page data not found")

        return json.parseToJsonElement(data).jsonObject["props"]!!.jsonObject
    }

    private fun JsonObject.toSManga(): SManga = SManga.create().apply {
        title = stringOrNull("title").orEmpty()
        setUrlWithoutDomain(stringOrNull("url").orEmpty())
        thumbnail_url = stringOrNull("cover")
    }

    private fun JsonObject.toChapter(): SChapter = SChapter.create().apply {
        setUrlWithoutDomain(stringOrNull("url").orEmpty())
        val chapterNumber = stringOrNull("number")
        val chapterTitle = stringOrNull("title")
        name = when {
            chapterNumber.isNullOrBlank() -> chapterTitle.orEmpty()
            chapterTitle.isNullOrBlank() -> "Chapter $chapterNumber"
            else -> "Chapter $chapterNumber - $chapterTitle"
        }
        date_upload = parseChapterDate(stringOrNull("date"))
    }

    private fun parseChapterDate(date: String?): Long {
        if (date.isNullOrBlank()) return 0L

        return runCatching {
            SimpleDateFormat("MMM d, yyyy", Locale.ENGLISH).parse(date)?.time ?: 0L
        }.getOrDefault(0L)
    }

    private fun JsonObject.stringOrNull(key: String): String? =
        this[key]?.jsonPrimitive?.contentOrNull
}
