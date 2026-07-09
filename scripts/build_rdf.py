#!/usr/bin/env python3
"""Build or append Zotero RDF from a transient metadata CSV.

Only Python standard-library modules are used. By default the script reads
paper_processed/.metadata_batch.csv, appends rows to paper_processed/processed.rdf,
appends collection assignments to paper_processed/collection_assignments.csv,
appends row notes to paper_processed/processing_notes.md, cleans processed source
inputs listed in the CSV, and then deletes the CSV.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET


NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "z": "http://www.zotero.org/namespaces/export#",
    "dcterms": "http://purl.org/dc/terms/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "bib": "http://purl.org/net/biblio#",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "link": "http://purl.org/rss/1.0/modules/link/",
    "prism": "http://prismstandard.org/namespaces/1.2/basic/",
}

for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def q(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


WORKSPACE = Path(__file__).resolve().parents[1]
PROCESSED_DIR = WORKSPACE / "paper_processed"
TO_PROCESS_DIR = WORKSPACE / "paper_to_be_processed"
DEFAULT_INPUT = PROCESSED_DIR / ".metadata_batch.csv"
DEFAULT_RDF = PROCESSED_DIR / "processed.rdf"
DEFAULT_NOTES = PROCESSED_DIR / "processing_notes.md"
DEFAULT_COLLECTION_ASSIGNMENTS = PROCESSED_DIR / "collection_assignments.csv"
DEFAULT_ASSIGN_SCRIPT = PROCESSED_DIR / "assign_collections.js"
DEFAULT_RULES = WORKSPACE / "Personal_rules.md"

FIELDNAMES = [
    "item_type",
    "title",
    "short_title",
    "authors",
    "doi",
    "url",
    "publication",
    "publisher",
    "volume",
    "issue",
    "pages",
    "issn",
    "journal_abbr",
    "date",
    "abstract",
    "language",
    "library_catalog",
    "extra",
    "collections",
    "pdf_path",
    "pdf_url",
    "attachment_title",
    "rdf_about",
    "source_file",
    "source_list_entry",
    "notes",
]

ASSIGNMENT_FIELDNAMES = [
    "timestamp",
    "title",
    "doi",
    "url",
    "rdf_about",
    "collections",
    "notes",
]

FALLBACK_COLLECTIONS = {
    "Clinical Study",
    "Spatial",
    "Spatial analysis",
    "Spatial benchmarking",
    "Spatial data & finding",
    "Spatial modeling",
    "Spatial wet tech",
    "Target Discovery",
}

PARENT_ONLY_COLLECTIONS = {"Spatial"}
SPATIAL_CHILDREN = {
    "Spatial analysis",
    "Spatial benchmarking",
    "Spatial data & finding",
    "Spatial modeling",
    "Spatial wet tech",
}

ITEM_TAGS = {
    "journalArticle": q("bib", "Article"),
    "preprint": q("rdf", "Description"),
    "conferencePaper": q("rdf", "Description"),
}


class ValidationError(Exception):
    pass


def clean_text(value: str | None) -> str:
    return (value or "").strip()


def split_multi(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def normalize_doi(value: str) -> str:
    doi = clean_text(value)
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    return doi.strip()


def doi_to_url(doi: str) -> str:
    return f"https://doi.org/{normalize_doi(doi)}"


def normalize_rdf_path(value: str) -> str:
    return clean_text(value).replace("\\", "/").lstrip("./")


def add_text(parent: ET.Element, tag: str, value: str | None) -> ET.Element | None:
    value = clean_text(value)
    if not value:
        return None
    child = ET.SubElement(parent, tag)
    child.text = value
    return child


def add_uri_identifier(parent: ET.Element, uri: str | None) -> None:
    uri = clean_text(uri)
    if not uri:
        return
    identifier = ET.SubElement(parent, q("dc", "identifier"))
    dcterms_uri = ET.SubElement(identifier, q("dcterms", "URI"))
    value = ET.SubElement(dcterms_uri, q("rdf", "value"))
    value.text = uri


def add_publisher(parent: ET.Element, publisher_name: str | None) -> None:
    publisher_name = clean_text(publisher_name)
    if not publisher_name:
        return
    publisher = ET.SubElement(parent, q("dc", "publisher"))
    organization = ET.SubElement(publisher, q("foaf", "Organization"))
    add_text(organization, q("foaf", "name"), publisher_name)


def parse_author(author: str) -> tuple[str, str]:
    author = clean_text(author)
    if "|" in author:
        surname, given = author.split("|", 1)
    elif "," in author:
        surname, given = author.split(",", 1)
    else:
        parts = author.split()
        if len(parts) == 1:
            surname, given = parts[0], ""
        else:
            surname, given = parts[-1], " ".join(parts[:-1])
    return clean_text(surname), clean_text(given)


def add_authors(parent: ET.Element, authors_value: str | None) -> None:
    authors = split_multi(authors_value)
    if not authors:
        return
    authors_element = ET.SubElement(parent, q("bib", "authors"))
    seq = ET.SubElement(authors_element, q("rdf", "Seq"))
    for author in authors:
        surname, given = parse_author(author)
        li = ET.SubElement(seq, q("rdf", "li"))
        person = ET.SubElement(li, q("foaf", "Person"))
        add_text(person, q("foaf", "surname"), surname)
        add_text(person, q("foaf", "givenName"), given)


def load_allowed_collections(path: Path) -> set[str]:
    if not path.exists():
        return set(FALLBACK_COLLECTIONS)
    text = path.read_text(encoding="utf-8-sig")
    in_collection_section = False
    allowed: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") and "分类" in stripped:
            in_collection_section = True
            continue
        if in_collection_section and stripped.startswith("## "):
            break
        if in_collection_section:
            match = re.match(r"-\s+`([^`]+)`", stripped)
            if match:
                allowed.add(match.group(1))
    return allowed or set(FALLBACK_COLLECTIONS)


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        raise ValidationError(f"Input CSV does not exist: {csv_path}")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValidationError("Input CSV is empty or missing a header row.")
        rows = []
        for raw_row in reader:
            row = {field: clean_text(raw_row.get(field, "")) for field in FIELDNAMES}
            rows.append(row)
    if not rows:
        raise ValidationError("Input CSV has no metadata rows.")
    return rows


def resolve_pdf_path(pdf_path: str, processed_dir: Path) -> Path:
    normalized = normalize_rdf_path(pdf_path)
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ValidationError(f"pdf_path must be relative to paper_processed: {pdf_path}")
    return processed_dir / Path(*normalized.split("/"))


def resolve_source_file(source_file: str, workspace: Path, to_process_dir: Path) -> Path:
    source = Path(source_file)
    if source.is_absolute():
        resolved = source.resolve()
    elif source.parts and source.parts[0] == to_process_dir.name:
        resolved = (workspace / source).resolve()
    else:
        resolved = (to_process_dir / source).resolve()
    process_root = to_process_dir.resolve()
    if not resolved.is_relative_to(process_root):
        raise ValidationError(f"source_file is outside paper_to_be_processed: {source_file}")
    if resolved.name == "paper_list.txt":
        raise ValidationError("Do not put paper_list.txt in source_file; use source_list_entry.")
    return resolved


def validate_rows(
    rows: list[dict[str, str]],
    allowed_collections: set[str],
    workspace: Path,
    processed_dir: Path,
    to_process_dir: Path,
) -> None:
    for row_number, row in enumerate(rows, start=2):
        if not row["item_type"]:
            raise ValidationError(f"Row {row_number}: item_type is required.")
        if row["item_type"] not in ITEM_TAGS:
            allowed_types = ", ".join(sorted(ITEM_TAGS))
            raise ValidationError(f"Row {row_number}: unsupported item_type {row['item_type']!r}; use {allowed_types}.")
        if not row["title"]:
            raise ValidationError(f"Row {row_number}: title is required.")
        for collection in split_multi(row["collections"]):
            if collection not in allowed_collections:
                raise ValidationError(f"Row {row_number}: unknown collection {collection!r}.")
            if collection in PARENT_ONLY_COLLECTIONS:
                raise ValidationError(f"Row {row_number}: {collection!r} is a parent-only collection.")
        if row["pdf_path"]:
            pdf_file = resolve_pdf_path(row["pdf_path"], processed_dir)
            if not pdf_file.exists():
                raise ValidationError(f"Row {row_number}: pdf_path does not exist: {pdf_file}")
            if not pdf_file.is_file():
                raise ValidationError(f"Row {row_number}: pdf_path is not a file: {pdf_file}")
        for source in split_multi(row["source_file"]):
            resolved = resolve_source_file(source, workspace, to_process_dir)
            if resolved.exists() and not resolved.is_file():
                raise ValidationError(f"Row {row_number}: source_file is not a file: {resolved}")


def load_or_create_rdf(path: Path) -> tuple[ET.ElementTree, ET.Element]:
    if path.exists() and path.stat().st_size > 0:
        tree = ET.parse(path)
        root = tree.getroot()
        if root.tag != q("rdf", "RDF"):
            raise ValidationError(f"Unexpected RDF root element in {path}: {root.tag}")
        return tree, root
    root = ET.Element(q("rdf", "RDF"))
    return ET.ElementTree(root), root


def strip_collection_elements(root: ET.Element) -> int:
    """Remove RDF collection nodes so Zotero won't create duplicate collections."""
    removed = 0
    for child in list(root):
        if child.tag == q("z", "Collection"):
            root.remove(child)
            removed += 1
    return removed


def next_item_number(root: ET.Element) -> int:
    max_number = 0
    for element in root.iter():
        about = element.attrib.get(q("rdf", "about"), "")
        match = re.fullmatch(r"#item_(\d+)", about)
        if match:
            max_number = max(max_number, int(match.group(1)))
    return max_number + 1


def create_item_resource(row: dict[str, str], next_id: int) -> tuple[str, int]:
    if row["rdf_about"]:
        return row["rdf_about"], next_id
    if row["url"]:
        return row["url"], next_id
    if row["doi"]:
        return doi_to_url(row["doi"]), next_id
    return f"#item_{next_id}", next_id + 1


def has_container(row: dict[str, str]) -> bool:
    if row["item_type"] not in {"journalArticle", "conferencePaper"}:
        return False
    return any(row[field] for field in ["publication", "doi", "volume", "issue", "issn", "journal_abbr"])


def add_container(parent: ET.Element, row: dict[str, str]) -> None:
    if not has_container(row):
        return
    is_part_of = ET.SubElement(parent, q("dcterms", "isPartOf"))
    journal = ET.SubElement(is_part_of, q("bib", "Journal"))
    if row["doi"]:
        add_text(journal, q("dc", "identifier"), f"DOI {normalize_doi(row['doi'])}")
    add_text(journal, q("prism", "volume"), row["volume"])
    add_text(journal, q("dc", "title"), row["publication"])
    if row["issn"]:
        add_text(journal, q("dc", "identifier"), f"ISSN {row['issn']}")
    add_text(journal, q("prism", "number"), row["issue"])
    add_text(journal, q("dcterms", "alternative"), row["journal_abbr"])


def add_item_doi(parent: ET.Element, row: dict[str, str]) -> None:
    if row["doi"]:
        add_text(parent, q("dc", "identifier"), f"DOI {normalize_doi(row['doi'])}")


def build_item_element(row: dict[str, str], resource: str, attachment_resource: str | None) -> ET.Element:
    item = ET.Element(ITEM_TAGS[row["item_type"]], {q("rdf", "about"): resource})
    add_text(item, q("z", "itemType"), row["item_type"])
    add_container(item, row)

    publisher = row["publisher"]
    if row["item_type"] == "preprint" and not publisher:
        publisher = row["publication"]
    add_publisher(item, publisher)
    add_authors(item, row["authors"])

    if attachment_resource:
        ET.SubElement(item, q("link", "link"), {q("rdf", "resource"): attachment_resource})

    add_text(item, q("dc", "subject"), "Codexed")
    add_text(item, q("dc", "title"), row["title"])
    add_text(item, q("dcterms", "abstract"), row["abstract"])
    add_text(item, q("dc", "date"), row["date"])
    add_item_doi(item, row)
    add_uri_identifier(item, row["url"] or (doi_to_url(row["doi"]) if row["doi"] else ""))
    add_text(item, q("z", "shortTitle"), row["short_title"])
    add_text(item, q("z", "language"), row["language"] or "en")
    add_text(item, q("z", "libraryCatalog"), row["library_catalog"])
    add_text(item, q("bib", "pages"), row["pages"])
    add_text(item, q("dc", "description"), row["extra"])
    return item


def build_attachment_element(row: dict[str, str], attachment_resource: str) -> ET.Element:
    attachment = ET.Element(q("z", "Attachment"), {q("rdf", "about"): attachment_resource})
    add_text(attachment, q("z", "itemType"), "attachment")
    add_text(attachment, q("dc", "title"), row["attachment_title"] or "PDF")
    if row["pdf_path"]:
        ET.SubElement(
            attachment,
            q("z", "path"),
            {q("rdf", "resource"): normalize_rdf_path(row["pdf_path"])},
        )
    elif row["pdf_url"]:
        add_uri_identifier(attachment, row["pdf_url"])
        add_text(attachment, q("z", "linkMode"), "1")
    add_text(attachment, q("link", "type"), "application/pdf")
    return attachment


def append_rows_to_rdf(rows: list[dict[str, str]], rdf_path: Path) -> dict[int, str]:
    tree, root = load_or_create_rdf(rdf_path)
    strip_collection_elements(root)
    item_number = next_item_number(root)
    item_resources: dict[int, str] = {}

    for row in rows:
        attachment_resource = None
        if row["pdf_path"] or row["pdf_url"]:
            attachment_resource = f"#item_{item_number}"
            item_number += 1

        item_resource, item_number = create_item_resource(row, item_number)
        item_resources[id(row)] = item_resource
        root.append(build_item_element(row, item_resource, attachment_resource))
        if attachment_resource:
            root.append(build_attachment_element(row, attachment_resource))

    rdf_path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="    ")
    tree.write(rdf_path, encoding="utf-8", xml_declaration=False, short_empty_elements=True)
    return item_resources


def append_collection_assignments(
    rows: list[dict[str, str]],
    assignments_path: Path,
    item_resources: dict[int, str],
) -> None:
    assignment_rows = []
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for row in rows:
        collections = "; ".join(split_multi(row["collections"]))
        if not collections:
            continue
        assignment_rows.append(
            {
                "timestamp": timestamp,
                "title": row["title"],
                "doi": normalize_doi(row["doi"]) if row["doi"] else "",
                "url": row["url"],
                "rdf_about": item_resources[id(row)],
                "collections": collections,
                "notes": row["notes"],
            }
        )

    if not assignment_rows:
        return

    assignments_path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not assignments_path.exists() or assignments_path.stat().st_size == 0
    with assignments_path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ASSIGNMENT_FIELDNAMES)
        if needs_header:
            writer.writeheader()
        writer.writerows(assignment_rows)


def collection_spec_for_zotero_js(collection: str) -> str:
    collection = clean_text(collection)
    if collection in SPATIAL_CHILDREN:
        return f"Spatial > {collection}"
    return collection


def read_assignment_entries(assignments_path: Path) -> list[dict[str, object]]:
    if not assignments_path.exists() or assignments_path.stat().st_size == 0:
        return []

    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    with assignments_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            title = clean_text(row.get("title", ""))
            doi = normalize_doi(row.get("doi", ""))
            url = clean_text(row.get("url", ""))
            if not title and not doi and not url:
                continue

            key = (doi, url, title)
            entry = grouped.setdefault(
                key,
                {
                    "title": title,
                    "doi": doi,
                    "url": url,
                    "collections": [],
                },
            )
            collections = entry["collections"]
            assert isinstance(collections, list)
            for collection in split_multi(row.get("collections", "")):
                spec = collection_spec_for_zotero_js(collection)
                if spec and spec not in collections:
                    collections.append(spec)

    entries = [entry for entry in grouped.values() if entry["collections"]]
    entries.sort(key=lambda entry: (str(entry["title"]).lower(), str(entry["doi"]), str(entry["url"])))
    return entries


ASSIGN_COLLECTIONS_JS_TEMPLATE = r'''// Run this in Zotero: Tools -> Developer -> Run JavaScript.
// Keep "Run as async function" enabled.
//
// Purpose:
//   After importing paper_processed/processed.rdf, assign the imported items to
//   existing Zotero collections without creating duplicate collections.
//   Spatial subcollections are matched by path, e.g. "Spatial > Spatial wet tech".

const LIBRARY_ID = Zotero.Libraries.userLibraryID;
const PREFER_TAG = "Codexed";

const ASSIGNMENTS = __ASSIGNMENTS_JSON__;

function normalizeDOI(value) {
  return (value || "")
    .trim()
    .replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "")
    .replace(/^doi:\s*/i, "")
    .toLowerCase();
}

function itemHasTag(item, tag) {
  if (!tag || !item.getTags) return false;
  return item.getTags().some((entry) => {
    if (typeof entry === "string") return entry === tag;
    return entry && entry.tag === tag;
  });
}

function itemDateAddedTime(item) {
  return Date.parse(item.dateAdded || item.getField?.("dateAdded") || "") || 0;
}

async function getChildCollections(collection) {
  const children = [];

  if (collection.getChildCollections) {
    try {
      const childIDsOrObjects = collection.getChildCollections(true);
      for (const child of childIDsOrObjects || []) {
        if (typeof child === "number") {
          children.push(Zotero.Collections.get(child));
        } else if (child) {
          children.push(child);
        }
      }
    } catch (error) {
      try {
        const childObjects = collection.getChildCollections();
        for (const child of childObjects || []) {
          if (child) children.push(child);
        }
      } catch (innerError) {
        // Fall through to other APIs below.
      }
    }
  }

  if (!children.length && Zotero.Collections.getByParent) {
    const childObjects = await Zotero.Collections.getByParent(collection.id);
    for (const child of childObjects || []) {
      if (child) children.push(child);
    }
  }

  return children.filter(Boolean);
}

async function walkCollections(collections, seen = new Set()) {
  const all = [];
  for (const collection of collections || []) {
    if (!collection || seen.has(collection.id)) continue;
    seen.add(collection.id);
    all.push(collection);
    all.push(...(await walkCollections(await getChildCollections(collection), seen)));
  }
  return all;
}

async function getAllCollections(libraryID) {
  if (Zotero.Collections.getAll) {
    let collections = Zotero.Collections.getAll(libraryID);
    if (collections && typeof collections.then === "function") {
      collections = await collections;
    }
    collections = (collections || []).filter((c) => c && c.libraryID === libraryID);
    if (collections.length) return collections;
  }

  if (Zotero.Collections.getByLibrary) {
    let collections = Zotero.Collections.getByLibrary(libraryID);
    if (collections && typeof collections.then === "function") {
      collections = await collections;
    }
    return walkCollections(collections || []);
  }

  throw new Error("Cannot list Zotero collections: unsupported Zotero.Collections API");
}

async function buildCollectionIndex(libraryID) {
  const collections = await getAllCollections(libraryID);
  const byName = new Map();
  const byID = new Map();
  for (const collection of collections) {
    if (!collection || !collection.name) continue;
    byID.set(collection.id, collection);
    if (!byName.has(collection.name)) byName.set(collection.name, []);
    byName.get(collection.name).push(collection);
  }
  return { byName, byID, all: collections };
}

function collectionChildCount(collection) {
  try {
    return collection.getChildItems(true).length;
  } catch (error) {
    return 0;
  }
}

function collectionPath(collection, collectionIndex) {
  const names = [];
  let current = collection;
  const seen = new Set();

  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    names.unshift(current.name);
    current = current.parentID ? collectionIndex.byID.get(current.parentID) : null;
  }

  return names.join(" > ");
}

function collectionMatchesPath(collection, pathParts, collectionIndex) {
  let current = collection;
  for (let i = pathParts.length - 1; i >= 0; i--) {
    if (!current || current.name !== pathParts[i]) return false;
    current = current.parentID ? collectionIndex.byID.get(current.parentID) : null;
  }
  return true;
}

function chooseCollection(collectionSpec, collectionIndex, warnings) {
  const pathParts = collectionSpec.split(">").map((part) => part.trim()).filter(Boolean);
  const collectionName = pathParts[pathParts.length - 1] || collectionSpec;
  let matches = collectionIndex.byName.get(collectionName) || [];

  if (pathParts.length > 1) {
    matches = matches.filter((collection) => collectionMatchesPath(collection, pathParts, collectionIndex));
  }

  if (!matches.length) return null;
  if (matches.length === 1) return matches[0];

  const sorted = matches.slice().sort((a, b) => {
    const countDiff = collectionChildCount(b) - collectionChildCount(a);
    if (countDiff) return countDiff;
    return a.id - b.id;
  });

  warnings.push(
    `Multiple collections matching "${collectionSpec}" found; using "${collectionPath(sorted[0], collectionIndex)}" id=${sorted[0].id}, key=${sorted[0].key}.`
  );
  return sorted[0];
}

async function searchItems(fieldName, value) {
  if (!value) return [];
  const search = new Zotero.Search();
  search.libraryID = LIBRARY_ID;
  search.addCondition("noChildren", "true");
  search.addCondition(fieldName, "is", value);
  const ids = await search.search();
  const items = await Zotero.Items.getAsync(ids);
  return items.filter((item) => item && item.isRegularItem && item.isRegularItem() && !item.deleted);
}

async function findBestItem(assignment, warnings) {
  let candidates = [];

  const doi = normalizeDOI(assignment.doi);
  if (doi) {
    candidates = await searchItems("DOI", doi);
    if (!candidates.length) {
      candidates = await searchItems("DOI", assignment.doi);
    }
  }

  if (!candidates.length && assignment.url) {
    candidates = await searchItems("url", assignment.url);
  }

  if (!candidates.length && assignment.title) {
    candidates = await searchItems("title", assignment.title);
  }

  if (!candidates.length) return null;

  const preferred = candidates.filter((item) => itemHasTag(item, PREFER_TAG));
  if (preferred.length) {
    candidates = preferred;
  }

  candidates.sort((a, b) => itemDateAddedTime(b) - itemDateAddedTime(a));

  if (candidates.length > 1) {
    warnings.push(
      `Multiple candidate items for "${assignment.title}"; using item id=${candidates[0].id}.`
    );
  }

  return candidates[0];
}

function itemCollectionIDs(item) {
  if (!item.getCollections) return [];
  return item.getCollections();
}

const collectionIndex = await buildCollectionIndex(LIBRARY_ID);
const summary = {
  assigned: 0,
  alreadyAssigned: 0,
  missingItems: [],
  missingCollections: [],
  warnings: [],
};

for (const assignment of ASSIGNMENTS) {
  const item = await findBestItem(assignment, summary.warnings);
  if (!item) {
    summary.missingItems.push(assignment.title);
    continue;
  }

  let changed = false;
  const existingCollectionIDs = new Set(itemCollectionIDs(item));

  for (const collectionName of assignment.collections) {
    const collection = chooseCollection(collectionName, collectionIndex, summary.warnings);
    if (!collection) {
      summary.missingCollections.push(collectionName);
      continue;
    }

    if (existingCollectionIDs.has(collection.id)) {
      summary.alreadyAssigned += 1;
      continue;
    }

    item.addToCollection(collection.id);
    existingCollectionIDs.add(collection.id);
    changed = true;
    summary.assigned += 1;
  }

  if (changed) {
    await item.saveTx();
  }
}

summary.missingCollections = [...new Set(summary.missingCollections)];
summary;
'''


def write_assign_collections_js(assignments_path: Path, script_path: Path) -> None:
    assignments = read_assignment_entries(assignments_path)
    assignments_json = json.dumps(assignments, ensure_ascii=False, indent=2)
    script = ASSIGN_COLLECTIONS_JS_TEMPLATE.replace("__ASSIGNMENTS_JSON__", assignments_json)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script, encoding="utf-8")


def append_notes(rows: list[dict[str, str]], notes_path: Path) -> None:
    notes = [(row["title"], row["notes"]) for row in rows if row["notes"]]
    if not notes:
        return
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with notes_path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## Batch {timestamp}\n\n")
        for title, note in notes:
            handle.write(f"- {title}: {note}\n")


def clean_processed_sources(
    rows: list[dict[str, str]],
    workspace: Path,
    to_process_dir: Path,
) -> None:
    source_files: list[Path] = []
    list_entries: set[str] = set()
    for row in rows:
        for source in split_multi(row["source_file"]):
            source_files.append(resolve_source_file(source, workspace, to_process_dir))
        list_entries.update(split_multi(row["source_list_entry"]))

    for source_file in source_files:
        if source_file.exists():
            source_file.unlink()

    list_path = to_process_dir / "paper_list.txt"
    if list_entries and list_path.exists():
        original_lines = list_path.read_text(encoding="utf-8").splitlines(keepends=True)
        kept_lines = [line for line in original_lines if line.strip() not in list_entries]
        list_path.write_text("".join(kept_lines), encoding="utf-8")


def write_template(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise ValidationError(f"Template target already exists: {path}. Use --force to overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append Zotero RDF records from a transient metadata CSV.")
    parser.add_argument("input_csv", nargs="?", default=str(DEFAULT_INPUT), help="Metadata CSV path.")
    parser.add_argument("--processed-rdf", default=str(DEFAULT_RDF), help="Target processed.rdf path.")
    parser.add_argument("--notes", default=str(DEFAULT_NOTES), help="Target processing_notes.md path.")
    parser.add_argument(
        "--collection-assignments",
        default=str(DEFAULT_COLLECTION_ASSIGNMENTS),
        help="Target collection_assignments.csv path.",
    )
    parser.add_argument("--assign-script", default=str(DEFAULT_ASSIGN_SCRIPT), help="Target assign_collections.js path.")
    parser.add_argument("--rules-file", default=str(DEFAULT_RULES), help="Personal_rules.md path.")
    parser.add_argument("--no-collection-assignments", action="store_true", help="Do not append collection assignments.")
    parser.add_argument("--no-assign-script", action="store_true", help="Do not write assign_collections.js.")
    parser.add_argument("--keep-input", action="store_true", help="Do not delete the input CSV after success.")
    parser.add_argument("--no-clean-sources", action="store_true", help="Do not delete processed source inputs.")
    parser.add_argument("--dry-run", action="store_true", help="Validate input without writing output or cleaning files.")
    parser.add_argument("--write-template", action="store_true", help="Create a blank metadata CSV template and exit.")
    parser.add_argument("--force", action="store_true", help="Overwrite when used with --write-template.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_csv = Path(args.input_csv).resolve()
    processed_rdf = Path(args.processed_rdf).resolve()
    notes_path = Path(args.notes).resolve()
    assignments_path = Path(args.collection_assignments).resolve()
    assign_script_path = Path(args.assign_script).resolve()
    rules_file = Path(args.rules_file).resolve()

    try:
        if args.write_template:
            write_template(input_csv, args.force)
            print(f"Wrote template: {input_csv}")
            return 0

        rows = read_rows(input_csv)
        allowed_collections = load_allowed_collections(rules_file)
        validate_rows(rows, allowed_collections, WORKSPACE, PROCESSED_DIR, TO_PROCESS_DIR)

        if args.dry_run:
            print(f"Validated {len(rows)} row(s). No files were changed.")
            return 0

        item_resources = append_rows_to_rdf(rows, processed_rdf)
        if not args.no_collection_assignments:
            append_collection_assignments(rows, assignments_path, item_resources)
        if not args.no_assign_script:
            write_assign_collections_js(assignments_path, assign_script_path)
        append_notes(rows, notes_path)
        if not args.no_clean_sources:
            clean_processed_sources(rows, WORKSPACE, TO_PROCESS_DIR)
        if not args.keep_input:
            input_csv.unlink()

        print(f"Appended {len(rows)} row(s) to {processed_rdf}")
        if not args.no_collection_assignments:
            print(f"Appended collection assignments to {assignments_path}")
        if not args.no_assign_script:
            print(f"Wrote Zotero collection assignment script to {assign_script_path}")
        if not args.no_clean_sources:
            print("Cleaned processed source inputs listed in the CSV.")
        if not args.keep_input:
            print(f"Deleted transient input CSV: {input_csv}")
        return 0
    except (ValidationError, ET.ParseError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
