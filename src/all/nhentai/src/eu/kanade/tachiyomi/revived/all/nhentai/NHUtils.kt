package eu.kanade.tachiyomi.revived.all.nhentai

import java.text.SimpleDateFormat
import java.util.Locale
import org.jsoup.nodes.Document
import org.jsoup.nodes.Element

object NHUtils {
    fun getArtists(document: Document): String {
        val artists = document.select("#tags > div:nth-child(4) > span > a .name")
        return artists.joinToString(", ") { it.cleanTag() }
    }

    fun getGroups(document: Document): String? {
        val groups = document.select("#tags > div:nth-child(5) > span > a .name")
        return if (groups.isNotEmpty()) {
            groups.joinToString(", ") { it.cleanTag() }
        } else {
            null
        }
    }

    fun getTagDescription(document: Document): String {
        val stringBuilder = StringBuilder()

        val categories = document.select("#tags > div:nth-child(7) > span > a .name")
        if (categories.isNotEmpty()) {
            stringBuilder.append("Categories: ")
            stringBuilder.append(categories.joinToString(", ") { it.cleanTag() })
            stringBuilder.append("\n\n")
        }

        val parodies = document.select("#tags > div:nth-child(1) > span > a .name")
        if (parodies.isNotEmpty()) {
            stringBuilder.append("Parodies: ")
            stringBuilder.append(parodies.joinToString(", ") { it.cleanTag() })
            stringBuilder.append("\n\n")
        }

        val characters = document.select("#tags > div:nth-child(2) > span > a .name")
        if (characters.isNotEmpty()) {
            stringBuilder.append("Characters: ")
            stringBuilder.append(characters.joinToString(", ") { it.cleanTag() })
        }

        return stringBuilder.toString()
    }

    fun getTags(document: Document): String {
        val tags = document.select("#tags > div:nth-child(3) > span > a .name")
        return tags.map { it.cleanTag() }.sorted().joinToString(", ")
    }

    fun getNumPages(document: Document): String {
        val pagesFromField = document
            .selectFirst("#tags .tag-container.field-name:matchesOwn((?i)^\\s*Pages:?\\s*$)")
            ?.nextElementSibling()
            ?.selectFirst("a .name")
            ?.cleanTag()

        val pagesFromLegacySelector = document
            .select("#tags > div:nth-child(8) > span > a .name")
            .firstOrNull()
            ?.cleanTag()

        return pagesFromField
            ?: pagesFromLegacySelector
            ?: "Unknown"
    }

    fun getTime(document: Document): Long {
        val timeString = document
            .selectFirst("#tags .tag-container.field-name:matchesOwn((?i)^\\s*Uploaded:?\\s*$)")
            ?.nextElementSibling()
            ?.selectFirst("time[datetime]")
            ?.attr("datetime")
            ?.takeIf { it.isNotBlank() }
            ?: document.selectFirst("time[datetime]")?.attr("datetime").orEmpty()

        if (timeString.isBlank()) return 0L

        val formats = listOf(
            "yyyy-MM-dd'T'HH:mm:ss.SSSSSSXXX",
            "yyyy-MM-dd'T'HH:mm:ss.SSSSSSZ",
            "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
            "yyyy-MM-dd'T'HH:mm:ss.SSSZ",
            "yyyy-MM-dd'T'HH:mm:ssXXX",
            "yyyy-MM-dd'T'HH:mm:ssZ",
        )

        return formats.firstNotNullOfOrNull { pattern ->
            runCatching {
                SimpleDateFormat(pattern, Locale.US).parse(timeString)?.time
            }.getOrNull()
        } ?: 0L
    }

    private fun Element.cleanTag(): String = text().replace(Regex("\\(.*\\)"), "").trim()
}
