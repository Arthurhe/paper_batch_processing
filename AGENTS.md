# 项目协作说明

本文件使用中文维护。处理本项目时，先读本文件，再读 `Personal_rules.md`；如果两者冲突，以 `Personal_rules.md` 中最新的个人规则为准。

## 项目目标

本项目用于把基础文献信息批量整理为 Zotero 可导入的 RDF 记录。用户把待处理文献放在 `paper_to_be_processed/`，处理完成后把结果持续追加到 `paper_processed/`，用户导入 Zotero 后会手动清理输出文件。

不要直接写入、修改或导入用户本机 Zotero 数据库，除非用户明确要求。

## 固定目录

- `paper_to_be_processed/`：用户放入待处理信息。处理完成后，必须删除或清空已经处理过的对应条目，避免下次重复处理。
- `paper_processed/processed.rdf`：Zotero RDF/XML 导入文件。该文件是持续追加型输出，不要因为新任务而清空或覆盖已有内容。
- `paper_processed/processing_notes.md`：持续追加型处理记录。不要因为新任务而清空或覆盖已有内容。
- `paper_processed/collection_assignments.csv`：持续追加型分类分配清单。RDF 不再写入 Zotero collection；导入 Zotero 后按此清单把条目放入已有分类。
- `paper_processed/assign_collections.js`：由 `scripts/build_rdf.py` 自动生成的 Zotero Developer Console 脚本。导入 RDF 后运行它，把条目加入已有 Zotero 分类；Spatial 子分类用 `Spatial > 子分类` 路径匹配。
- `paper_processed/files/`：处理后的 PDF 附件目录。
- `paper_processed/.metadata_batch.csv`：临时中间表，是 `scripts/build_rdf.py` 的默认输入。脚本成功运行后会自动删除；失败时保留，方便修正后重试。

## 输入形式

`paper_to_be_processed/` 中可能出现两类输入：

1. `paper_to_be_processed/paper_list.txt`：每行一篇文献，可以是 DOI、arXiv/bioRxiv 号、PMID、论文网页 URL、PDF 下载 URL 等。通常这里的链接应能打开论文页面或直接下载 PDF。
2. 直接放入的 PDF 文件：需要用 PDF/文本抽取工具读取元数据、摘要、作者、DOI、出版信息等。

以后新处理任务不再依赖 `我的文库.rdf`，也不需要对照既有 Zotero 文库结构。不要做查重；重复条目后续由用户在 Zotero 中处理。

## 中间表到 RDF

使用 `scripts/build_rdf.py` 把临时中间表转换并追加到 RDF。该脚本只使用 Python 标准库，不需要安装第三方包。

默认流程：

1. 抽取文献信息并整理 PDF 到 `paper_processed/files/`。
2. 生成临时中间表 `paper_processed/.metadata_batch.csv`。
3. 运行 `python scripts/build_rdf.py`。
4. 脚本会追加写入 `paper_processed/processed.rdf`，把分类分配追加到 `paper_processed/collection_assignments.csv`，重写 `paper_processed/assign_collections.js`，把 `notes` 字段追加到 `paper_processed/processing_notes.md`，删除中间表，并清理中间表中标记过的已处理源输入。

可用下面命令生成空表头：

```powershell
python scripts/build_rdf.py --write-template
```

中间表必须放在 `paper_processed/.metadata_batch.csv`。这是临时 CSV，UTF-8 编码，首行必须是以下表头；多值字段用英文分号 `;` 分隔：

```csv
item_type,title,short_title,authors,doi,url,publication,publisher,volume,issue,pages,issn,journal_abbr,date,abstract,language,library_catalog,extra,collections,pdf_path,pdf_url,attachment_title,rdf_about,source_file,source_list_entry,notes
```

详细字段定义见 `scripts/metadata_batch_schema.md`。关键字段：

- `item_type`：必填，当前支持 `journalArticle`、`preprint`、`conferencePaper`。
- `title`：必填。
- `authors`：只填第一作者和最后通讯作者，格式为 `Surname, Given; Surname, Given`。
- `collections`：用 `;` 分隔多个分类，只能使用 `Personal_rules.md` 中允许的分类，不能直接填父分类 `Spatial`。该字段写入 `collection_assignments.csv`，不要写成 RDF collection。
- `pdf_path`：本地 PDF 路径，相对 `paper_processed/`，例如 `files/example.pdf`。
- `pdf_url`：无本地 PDF 时可写公开 PDF URL。
- `source_file`：处理成功后要从 `paper_to_be_processed/` 删除的源 PDF 文件名，多个用 `;` 分隔。
- `source_list_entry`：处理成功后要从 `paper_to_be_processed/paper_list.txt` 删除的原始行，多个用 `;` 分隔。
- `notes`：脚本会追加到 `processing_notes.md`。

如果脚本报错，不要手动删除 `.metadata_batch.csv`，先修正错误后重跑。只有成功运行后中间表才应该消失。

## 信息抽取要求

每篇文献至少尽力填写：

- 条目类型：常见为 `journalArticle`、`preprint`、`conferencePaper`。不确定时选择最接近的类型，并在 notes 说明。
- 作者：只填写第一作者和最后一个通讯作者。若无法确认通讯作者，填写第一作者和最后一位作者，并在 notes 说明。
- DOI。
- 网址：论文主页面 URL，优先出版社页面，其次 DOI 页面或预印本页面。
- 标题。
- 短标题：方法学文章优先填技术、平台、模型或工具名称；非方法文章填能概括核心对象或发现的短语。
- 出版物：期刊、会议或预印本平台名称。
- 卷次、页码、ISSN、期号：找得到就填，找不到不强求。
- 刊名简称：例如 `Nature`、`Nat Commun`。
- 摘要。
- 日期。
- 语言：通常为 `en`。
- 其他/Extra：用 `Data: ...` 填写文章使用的组学技术平台类型，例如 `Data: Xenium+Flex`。无法判断时留空，不要编造。

优先从出版社页面、Crossref、PubMed、arXiv/bioRxiv、论文 PDF 首页和补充信息抽取。对最新论文或网页元数据，必要时联网核验。

## 分类与标签

分类和标签规则维护在 `Personal_rules.md`。

分类是 Zotero 的主要管理方式，只能使用 `Personal_rules.md` 中列出的分类。不要自创新分类。Zotero 允许一篇文献属于多个分类；拿不定时宁可不加分类，并在 `processing_notes.md` 说明。

Tag 是辅助标识系统。当前不要自创 Tag；除非 `Personal_rules.md` 另有更新，否则忽略 Tag。

## RDF 生成规则

不要手写最终 RDF。除非用户特别要求，最终都应通过 `scripts/build_rdf.py` 从 `.metadata_batch.csv` 生成。

脚本生成的 RDF 使用 Zotero RDF/XML，包含常用 namespace：

- `rdf`: `http://www.w3.org/1999/02/22-rdf-syntax-ns#`
- `z`: `http://www.zotero.org/namespaces/export#`
- `dcterms`: `http://purl.org/dc/terms/`
- `dc`: `http://purl.org/dc/elements/1.1/`
- `bib`: `http://purl.org/net/biblio#`
- `foaf`: `http://xmlns.com/foaf/0.1/`
- `link`: `http://purl.org/rss/1.0/modules/link/`
- `prism`: `http://prismstandard.org/namespaces/1.2/basic/`

PDF 附件作为文献条目的子附件写入：父条目用 `<link:link rdf:resource="#item_N"/>` 指向附件，附件节点使用 `<z:Attachment rdf:about="#item_N">`。本地 PDF 优先使用相对路径，例如 `files/example.pdf`；没有本地 PDF 时可使用公开 `pdf_url` 生成远程附件。

不要在 RDF 中写 `<z:Collection>`。Zotero 导入 RDF 时不会把同名 collection 合并到已有分类，而是会创建新的同名分类；即使没有勾选“将导入的分类和条目放入新分类”，RDF 内部的 collection 节点仍会作为新 collection 导入。因此分类只写入 `paper_processed/collection_assignments.csv`，并由脚本自动生成 `paper_processed/assign_collections.js`。

用户导入 `processed.rdf` 后，应在 Zotero 中打开 `Tools -> Developer -> Run JavaScript`，保持 `Run as async function` 勾选，粘贴并运行 `assign_collections.js`。该脚本按 DOI、URL、标题查找导入条目，优先匹配 `Codexed` tag 和最新导入项，再按已有 collection 名称或路径加入分类。`Spatial ...` 子分类必须自动写成 `Spatial > Spatial ...` 路径，避免因为子分类层级导致添加失败。

## 处理后清理

每次任务完成后必须清理已经处理过的输入：

- 对 `paper_list.txt` 中已经处理的行，在 `.metadata_batch.csv` 的 `source_list_entry` 字段填入原始行；脚本成功后会删除这些行。
- 对直接提供并已经处理的 PDF，在 `source_file` 字段填入文件名；脚本成功后会删除对应源文件。
- 如果某个输入没有成功生成 RDF 条目，不要清理它，留到下次继续处理。

清理只针对 `paper_to_be_processed/` 内的文件和 `paper_list.txt` 行。不要删除 `paper_processed/` 中已经整理好的 PDF。

## 工作流程

1. 读取 `Personal_rules.md` 和本文件。
2. 扫描 `paper_to_be_processed/`，收集 `paper_list.txt` 和 PDF。
3. 对每篇文献抽取元数据；能联网时优先核验 DOI、出版社 URL、出版物、卷期页码。
4. 下载或整理 PDF 到 `paper_processed/files/`；无法获取 PDF 时仍可生成元数据条目。
5. 按 `Personal_rules.md` 判断分类；拿不定就不分类，并写入 notes。
6. 写入 `paper_processed/.metadata_batch.csv`。
7. 运行 `python scripts/build_rdf.py`。
8. 确认 `processed.rdf` 是合法 XML 且不包含 `<z:Collection>`，确认附件路径存在，确认 `collection_assignments.csv` 已追加分类分配，确认 `assign_collections.js` 已生成且语法可用，确认已处理输入已从 `paper_to_be_processed/` 清理，中间表已删除。

## 质量要求

- 不编造 DOI、作者、卷期页码、ISSN、通讯作者、平台类型。
- 对无法确定的字段留空或记录在 notes，不要用低置信度内容填充。
- 不做查重，不因怀疑重复而跳过条目。
- 不清空 `processed.rdf` 或 `processing_notes.md`；它们由用户导入 Zotero 后手动清理。
- 所有输出文件应能被用户直接检查；不要把无关中间缓存混入 `paper_processed/`。
- 任何需要登录、付费或绕过访问控制的下载都不要尝试；只使用合法公开可访问来源或用户提供的 PDF。
- 修改个人规则时，只编辑 `Personal_rules.md`，并保留既有分类名，除非用户明确要求更名。
