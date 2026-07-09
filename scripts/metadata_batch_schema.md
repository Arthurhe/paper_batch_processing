# metadata_batch.csv 中间表格式

中间表默认路径是 `paper_processed/.metadata_batch.csv`。这是临时文件：运行 `python scripts/build_rdf.py` 成功后会被自动删除；失败时保留，方便修改后重试。

脚本会把 Zotero 可导入条目追加到 `paper_processed/processed.rdf`，但不会在 RDF 中写入 `<z:Collection>`。分类信息会另行追加到 `paper_processed/collection_assignments.csv`，并自动重写 `paper_processed/assign_collections.js`。导入 Zotero 后运行该 JS，把新条目加入已有分类。

可用下面命令生成空表头：

```powershell
python scripts/build_rdf.py --write-template
```

默认执行命令：

```powershell
python scripts/build_rdf.py
```

## 字段

CSV 使用 UTF-8 编码，第一行必须是表头。多值字段用英文分号 `;` 分隔。

- `item_type`：必填。当前支持 `journalArticle`、`preprint`、`conferencePaper`。
- `title`：必填。论文完整标题。
- `short_title`：Zotero 短标题，方法学文章优先填模型、技术、平台或工具名。
- `authors`：只填第一作者和最后通讯作者，格式为 `Surname, Given; Surname, Given`。也兼容 `Surname|Given`。
- `doi`：DOI，可写 `10.xxxx`、`doi:10.xxxx` 或 DOI URL。
- `url`：论文主页面 URL。
- `publication`：期刊、会议或预印本平台名称。
- `publisher`：出版方。预印本如果留空，会用 `publication` 写入 publisher。
- `volume`：卷次。
- `issue`：期号。
- `pages`：页码。
- `issn`：ISSN，可含多个值。
- `journal_abbr`：刊名简称。
- `date`：发表日期。
- `abstract`：摘要。
- `language`：语言，留空时脚本写 `en`。
- `library_catalog`：来源目录，找不到可留空。
- `extra`：Zotero Extra，例如 `Data: Xenium+Flex`。
- `collections`：分类，多个用 `;` 分隔；只能使用 `Personal_rules.md` 中允许的分类，不能直接写父分类 `Spatial`。该字段不会写入 RDF collection，而是写入 `collection_assignments.csv`。
- `pdf_path`：本地 PDF 路径，相对 `paper_processed/`，例如 `files/s41588-025-02193-3.pdf`。
- `pdf_url`：公开 PDF URL；仅在没有 `pdf_path` 时用于远程附件。
- `attachment_title`：附件标题，留空时为 `PDF`。
- `rdf_about`：RDF 资源 ID，通常留空；脚本会优先用 `url`，其次 DOI URL。
- `source_file`：处理完成后要从 `paper_to_be_processed/` 删除的源文件名，多个用 `;` 分隔，例如 `s41588-025-02193-3.pdf`。
- `source_list_entry`：处理完成后要从 `paper_to_be_processed/paper_list.txt` 删除的原始行，多个用 `;` 分隔。
- `notes`：需要追加到 `paper_processed/processing_notes.md` 的说明。

## 最小示例

```csv
item_type,title,short_title,authors,doi,url,publication,publisher,volume,issue,pages,issn,journal_abbr,date,abstract,language,library_catalog,extra,collections,pdf_path,pdf_url,attachment_title,rdf_about,source_file,source_list_entry,notes
journalArticle,Example title,Example,"Doe, Jane; Smith, John",10.1000/example,https://example.org/article,Nature,,,,,,Nature,2026-01-01,Abstract text,en,DOI.org (Crossref),Data: Xenium,Spatial data & finding,files/example.pdf,,PDF,,example.pdf,https://example.org/article,
```

## 分类分配输出

`paper_processed/collection_assignments.csv` 是持续追加文件，默认字段为：

- `timestamp`：脚本执行时间。
- `title`：论文标题。
- `doi`：DOI。
- `url`：论文 URL。
- `rdf_about`：RDF 中使用的资源 ID，通常等于 URL。
- `collections`：应分配到的已有 Zotero 分类，多个用 `;` 分隔。
- `notes`：来自中间表的 notes。

Zotero RDF 导入不会把同名 collection 自动合并到已有分类；如果在 RDF 中写 `<z:Collection>`，Zotero 会新建同名分类。因此本项目把分类分配从 RDF 中拆出来。

`paper_processed/assign_collections.js` 会根据该 CSV 自动生成。生成时会把 `Spatial` 下的子分类写成路径形式，例如：

- `Spatial data & finding` -> `Spatial > Spatial data & finding`
- `Spatial wet tech` -> `Spatial > Spatial wet tech`

导入 `processed.rdf` 后，在 Zotero 的 `Tools -> Developer -> Run JavaScript` 中运行该 JS，并保持 `Run as async function` 勾选。
