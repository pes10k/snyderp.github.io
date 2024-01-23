import enum
import dataclasses
import datetime
import html
import json
from operator import attrgetter
from pathlib import Path
from typing import Any, cast, Dict, Generic, Literal, List
from typing import Optional, Type, TypeVar, Union

from .indent import Indenter
from .types import Author, Date, Html, Link, PubNote, Source, TalkType, Url
from .types import Venue, Year


def is_local_file_ref(ref: Optional[str]) -> bool:
    if not ref:
        return False
    if "//" in ref:  # Looks like a HTTP link
        return False
    return True


def add_desc_html(desc: str, markup: Indenter) -> None:
    markup.add(f"<span class='description'>{desc}</span>")


def add_authors_html(authors: List[Author], markup: Indenter) -> None:
    if len(authors) == 0:
        return
    markup.add("<ol class='authors'>").up()
    for author in authors:
        markup.add(f"<li>{author.to_html()}</li>")
    markup.down().add("</ol>")


def add_coauthors_html(authors: List[Author], markup: Indenter) -> None:
    non_me_authors = []
    for an_author in authors:
        if an_author.abbr != "@me":
            non_me_authors.append(an_author)
    if len(non_me_authors) == 0:
        return
    markup.add("<div class='co-authors-sec'>").up()
    markup.add("<span class='co-authors-desc'>Written with:</span>")
    markup.add("<ol class='authors co-authors'>").up()
    for author in non_me_authors:
        markup.add(f"<li>{author.to_html()}</li>")
    markup.down().add("</ol>")
    markup.down().add("</div>")


def add_links_html(links: List[Link], markup: Indenter) -> None:
    if len(links) == 0:
        return
    start_tag = "<span class='label label-default pub-link'>"
    end_tag = "</span>"

    markup.add("<span class='pub-links'>").up()
    for link in links:
        markup.add(f"{start_tag}{link.to_html()}{end_tag}")
    markup.down().add("</span>")


def add_notes_and_links_html(notes: List[PubNote], links: List[Link],
                             markup: Indenter) -> None:
    if len(links) == 0 and len(notes) == 0:
        return

    markup.add("<span class='pub-links'>").up()
    if len(notes) > 0:
        for note in notes:
            markup.add(note.to_html())

    if len(links) > 0:
        start_tag = "<span class='label label-default pub-link'>"
        end_tag = "</span>"
        for link in links:
            markup.add(f"{start_tag}{link.to_html()}{end_tag}")
    markup.down().add("</span>")


def add_dest_html(dest: Union[Source, Venue], list_item: "ListItem",
                  markup: Indenter) -> None:
    markup.add("<span class='venue'>").up()
    markup.add(dest.to_html())
    markup.add(list_item.date_html())
    markup.down().add("</span>")


def add_date_html(date: Union[Date, Year], list_item: "ListItem",
                  markup: Indenter) -> None:
    markup.add("<span class='venue'>").up()
    markup.add(list_item.date_html())
    markup.down().add("</span>")


def authors_from_json(item_data: Dict[str, Any],
                      all_data: Dict[str, Any]) -> List[Author]:
    authors: List[Author] = []
    try:
        authors_data = item_data["authors"]
    except KeyError:
        return authors

    for author in authors_data:
        if author[0] == "@":
            author_title = all_data["abbrs"]["authors"][author]
            authors.append(Author(author_title, author))
        else:
            authors.append(Author(author))
    return authors


def source_from_json(item_data: Dict[str, Any],
                     all_data: Dict[str, Any]) -> Source:
    source_abbr = item_data["source"]
    source_data = all_data["abbrs"]["sources"][source_abbr]
    return Source(source_data["title"], source_data["url"], source_abbr)


def year_from_json(item_data: Union[str, int]) -> int:
    if isinstance(item_data, str):
        if item_data != "@now":
            raise BaseException(f'Invalid year value in json: {item_data}')
        return datetime.datetime.now().year
    return item_data


def talk_type_from_json(item_data: Dict[str, Any],
                        all_data: Dict[str, Any]) -> TalkType:
    raw_talk_type = item_data["type"]
    if raw_talk_type[0] == "@":
        return TalkType(**all_data["abbrs"]["types"][raw_talk_type])
    return TalkType(raw_talk_type)


def venue_from_json(item_data: Dict[str, Any],
                    all_data: Dict[str, Any]) -> Venue:
    raw_venue = item_data["venue"]
    if raw_venue[0] == "@":
        return Venue(**all_data["abbrs"]["venues"][raw_venue])
    return Venue(raw_venue)


def date_from_json(item_data: Dict[str, Any]) -> datetime.datetime:
    date_str = item_data["date"]
    return datetime.datetime.fromisoformat(date_str)


def pub_notes_from_json(item_data: Dict[str, Any]) -> List[PubNote]:
    try:
        return [PubNote(note) for note in item_data["notes"]]
    except KeyError:
        return []


def links_from_json(item_data: Dict[str, Any]) -> List[Link]:
    try:
        links_data = item_data["links"]
        links = [Link(k, v) for k, v in links_data.items()]
        return sorted(links, key=lambda x: x.title)
    except KeyError:
        return []


class BaseItem:
    html_classes: List[str] = []
    file_fields: List[str] = []

    def add_html(self, markup: Indenter, prior_item: Optional[Any]) -> None:
        raise NotImplementedError()

    def validate(self, root_dir: Path) -> bool:
        possible_files: List[str] = []
        for file_field_name in type(self).file_fields:
            field_values = getattr(self, file_field_name)
            if not isinstance(field_values, list):
                field_values = [field_values]
            for a_field_value in field_values:
                if isinstance(a_field_value, dict):
                    possible_files.extend(a_field_value.values())
                    continue
                if isinstance(a_field_value, Link):
                    possible_files.append(a_field_value.url)
                    continue
                possible_files.append(a_field_value)
        for a_ref in possible_files:
            if not is_local_file_ref(a_ref):
                continue
            possible_file_path = root_dir / Path(a_ref)
            if not possible_file_path.is_file():
                raise FileNotFoundError(str(possible_file_path))
        return True

    @staticmethod
    def sort(items: List["BaseItem"]) -> List["BaseItem"]:
        return sorted(items, key=attrgetter("date"), reverse=True)

    @classmethod
    def add_list_html(cls, items: List["BaseItem"], markup: Indenter) -> None:
        class_str = " ".join(cls.html_classes)
        markup.add(f"<ul class='{class_str}'>").up()
        prior_item = None
        for item in items:
            item.add_html(markup, prior_item)
            prior_item = item
        markup.down().add("</ul>")

    @classmethod
    def list_from_json(cls, data: Dict[str, Any]) -> List["BaseItem"]:
        items: List["BaseItem"] = []
        for item in data["items"]:
            items.append(cls.item_from_json(item, data))
        return items

    @staticmethod
    def item_from_json(item_data: Dict[str, Any],
                       all_data: Dict[str, Any]) -> "BaseItem":
        raise NotImplementedError()


class ListItem(BaseItem):
    html_classes = ["publications"]
    file_fields = ["url"]

    date: Date
    title: str
    url: Optional[Url]

    def __init__(self, date: Date, title: str, url: Optional[Url]) -> None:
        self.date = date
        self.title = title
        self.url = url

    def title_html(self) -> Html:
        safe_title = html.escape(self.title)
        if self.url:
            return f"<a class='pub-title' href='{self.url}'>{safe_title}</a>"
        return f"<span class='pub-title'>{safe_title}</span>"

    def date_html(self) -> Html:
        date_line = ""
        date_value = ""
        try:
            date_as_datetime = cast(datetime.datetime, self.date)
            date_line = date_as_datetime.strftime("%b %d, %Y")
            date_value = date_as_datetime.strftime("%Y-%m-%d")
        except AttributeError:
            date_line = str(self.date)
            date_value = date_line
        return f"<time datetime='{date_value}'>{date_line}</time>"


class BlogItem(ListItem):
    html_classes = ["publications", "publications-blog"]

    source: Source
    authors: List[Author]
    desc = Optional[Type[str]]

    def __init__(self, date: Date, title: str, url: Url, source: Source,
                 authors: List[Author], desc: Optional[str]) -> None:
        self.authors = authors
        self.source = source
        self.desc = desc
        super().__init__(date, title, url)

    def add_html(self, markup: Indenter, prior_item: Optional[Any]) -> None:
        markup.add("<li>").up()
        markup.add(self.title_html())
        add_coauthors_html(self.authors, markup)
        add_dest_html(self.source, self, markup)
        if self.desc:
            add_desc_html(str(self.desc), markup)
        markup.down().add("</li>")

    @staticmethod
    def item_from_json(item_data: Dict[str, Any],
                       all_data: Dict[str, Any]) -> "BlogItem":
        date = date_from_json(item_data)
        authors = authors_from_json(item_data, all_data)
        source = source_from_json(item_data, all_data)
        desc = item_data["desc"] if "desc" in item_data else None
        return BlogItem(date, item_data["title"], item_data["url"],
                        source, authors, desc)


@dataclasses.dataclass
class PublicationItem(ListItem):
    file_fields = ["url", "links"]

    authors: List[Author]
    links: List[Link]
    venue: Venue
    notes: List[PubNote]

    def __init__(self, year: Year, title: str, url: Optional[Url],
                 authors: List[Author], links: List[Link],
                 venue: Venue, notes: List[PubNote]) -> None:
        self.authors = authors
        self.links = links
        self.venue = venue
        self.notes = notes
        super().__init__(year, title, url)

    def add_html(self, markup: Indenter, prior_item: Optional[Any]) -> None:
        markup.add("<li>").up()
        markup.add(self.title_html())
        add_authors_html(self.authors, markup)
        add_dest_html(self.venue, self, markup)
        add_notes_and_links_html(self.notes, self.links, markup)
        markup.down().add("</li>")

    @staticmethod
    def item_from_json(item_data: Dict[str, Any],
                       all_data: Dict[str, Any]) -> "PublicationItem":
        year = year_from_json(item_data["year"])
        authors = authors_from_json(item_data, all_data)
        links = links_from_json(item_data)
        venue = venue_from_json(item_data, all_data)
        url = item_data["url"] if "url" in item_data else None
        notes = pub_notes_from_json(item_data)
        return PublicationItem(year, item_data["title"], url, authors,
                               links, venue, notes)


@dataclasses.dataclass
class InvolvementItem(BaseItem):
    venue: Venue
    position: str
    date: Year

    def add_html(self, markup: Indenter, prior_item: Optional[Any]) -> None:
        should_add_header = False
        if not prior_item or self.date != prior_item.date:
            markup.add("<tr>").up()
            markup.add(f'<th colspan="2" class="year active">{self.date}</th>')
            markup.down().add("</tr>")

        markup.add("<tr>").up()
        markup.add(f'<td class="venue">{self.venue.to_html()}</td>')
        markup.add(f'<td class="position">{html.escape(self.position)}</td>')
        markup.down().add("</tr>")

    @classmethod
    def add_list_html(cls, items: List["BaseItem"], markup: Indenter) -> None:
        prior_item = None
        for item in items:
            item.add_html(markup, prior_item)
            prior_item = item

    @staticmethod
    def item_from_json(item_data: Dict[str, Any],
                       all_data: Dict[str, Any]) -> "InvolvementItem":
        raw_venue = item_data["venue"]
        if raw_venue[0] == "@":
            venue = Venue(**all_data["abbrs"]["venues"][raw_venue])
        else:
            venue = Venue(raw_venue)

        raw_position = item_data["position"]
        position = all_data["abbrs"]["positions"][raw_position]
        date = item_data["year"]
        return InvolvementItem(venue, position, date)


class PressItem(ListItem):
    ITEM_TYPE_CLASSES = {
        "news": "success",
        "podcast": "primary",
        "radio": "warning",
        "video": "info"
    }
    html_classes = ["publications", "publications-press"]

    source: Source
    type: str

    def __init__(self, date: datetime.datetime, title: str, url: Url,
                 source: Source, item_type: str) -> None:
        if item_type not in PressItem.ITEM_TYPE_CLASSES:
            raise ValueError(f"{item_type} is not a valid PressItem type")
        self.source = source
        self.type = item_type
        super().__init__(date, title, url)

    def add_type_markup(self, markup: Indenter) -> None:
        type_markup = html.escape(self.type)
        markup.add("<span class='press-type'>").up()
        type_class = PressItem.ITEM_TYPE_CLASSES[self.type]
        pill_classes = f"label label-{type_class}"
        pill_html = f"<span class='{pill_classes}'>{type_markup}</span>"
        markup.add(pill_html).down()
        markup.add("</span>")

    def add_html(self, markup: Indenter, prior_item: Optional[Any]) -> None:
        markup.add("<li>").up()
        markup.add(self.title_html())
        self.add_type_markup(markup)
        add_dest_html(self.source, self, markup)
        markup.down().add("</li>")

    @staticmethod
    def item_from_json(item_data: Dict[str, Any],
                       all_data: Dict[str, Any]) -> "PressItem":
        date = date_from_json(item_data)
        source = source_from_json(item_data, all_data)
        return PressItem(date, item_data["title"], item_data["url"],
                         source, item_data["type"])


class TalksItem(ListItem):
    html_classes = ["publications", "publications-talks"]
    file_fields = ["url", "links"]

    type: TalkType
    links: List[Link]
    venue: Venue
    authors: List[Author]

    def __init__(self, year: Year, title: str, item_type: TalkType,
                 url: Optional[Url], links: List[Link], venue: Venue,
                 authors: List[Author]) -> None:
        self.links = links
        self.venue = venue
        self.type = item_type
        self.authors = authors
        super().__init__(year, title, url)

    def add_html(self, markup: Indenter, prior_item: Optional[Any]) -> None:
        markup.add("<li>").up()
        markup.add(self.title_html())
        if len(self.authors) > 0:
            add_authors_html(self.authors, markup)
        add_dest_html(self.venue, self, markup)
        markup.add(self.type.to_html())
        add_links_html(self.links, markup)
        markup.down().add("</li>")

    @staticmethod
    def item_from_json(item_data: Dict[str, Any],
                       all_data: Dict[str, Any]) -> "TalksItem":
        year = year_from_json(item_data["year"])
        links = links_from_json(item_data)
        talk_type = talk_type_from_json(item_data, all_data)
        venue = venue_from_json(item_data, all_data)
        authors = authors_from_json(item_data, all_data)
        url = item_data["url"] if "url" in item_data else None
        return TalksItem(year, item_data["title"], talk_type, url, links,
                         venue, authors)


class WritingItem(ListItem):
    html_classes = ["publications", "publications-other-writing"]
    file_fields = ["url", "links"]

    links: List[Link]
    venue: Optional[Venue]
    desc: str
    authors: List[Author]

    def __init__(self, year: Year, title: str, url: Url, links: List[Link],
                 venue: Optional[Venue], desc: str,
                 authors: List[Author]) -> None:
        self.links = links
        self.venue = venue
        self.desc = desc
        self.authors = authors
        super().__init__(year, title, url)

    def add_html(self, markup: Indenter, prior_item: Optional[Any]) -> None:
        markup.add("<li>").up()
        markup.add(self.title_html())
        add_authors_html(self.authors, markup)
        if self.venue:
            add_dest_html(self.venue, self, markup)
        else:
            add_date_html(self.date, self, markup)
        add_links_html(self.links, markup)
        add_desc_html(self.desc, markup)
        markup.down().add("</li>")

    @staticmethod
    def item_from_json(item_data: Dict[str, Any],
                       all_data: Dict[str, Any]) -> "WritingItem":
        year = year_from_json(item_data["year"])
        links = links_from_json(item_data)
        url = item_data["url"] if "url" in item_data else None
        venue = None
        if "venue" in item_data:
            venue = venue_from_json(item_data, all_data)
        authors = authors_from_json(item_data, all_data)
        return WritingItem(year, item_data["title"], url, links,
                           venue, item_data["desc"], authors)


class CodeItem(ListItem):
    html_classes = ["publications"]
    file_fields = ["links"]

    links: List[Link]
    desc: str

    def __init__(self, year: Year, title: str, url: Url, links: List[Link],
                 desc: str) -> None:
        self.links = links
        self.desc = desc
        super().__init__(year, title, url)

    def add_html(self, markup: Indenter, prior_item: Optional[Any]) -> None:
        markup.add("<li>").up()
        markup.add(self.title_html())
        add_date_html(self.date, self, markup)
        add_links_html(self.links, markup)
        add_desc_html(self.desc, markup)
        markup.down().add("</li>")

    @staticmethod
    def item_from_json(item_data: Dict[str, Any],
                       all_data: Dict[str, Any]) -> "CodeItem":
        year = year_from_json(item_data["year"])
        links = links_from_json(item_data)
        url = item_data["url"] if "url" in item_data else None
        return CodeItem(year, item_data["title"], url, links,
                        item_data["desc"])
