# paper_batch_processing

这个项目用于把待处理文献批量整理成 Zotero 可导入的 RDF 记录，并把 PDF 附件和分类分配一并整理好。

## 目录说明

- `paper_to_be_processed/`：放待处理文献。可以是 PDF，也可以在 `paper_list.txt` 中逐行写 DOI、论文链接或 PDF 链接。
- `paper_processed/`：放处理结果。用户导入 Zotero 后可手动清理。
- `paper_processed/files/`：处理后的 PDF 附件。
- `scripts/build_rdf.py`：从临时中间表生成/追加 Zotero RDF、分类分配清单和 Zotero 分类脚本。
- `Personal_rules.md`：个人文库分类和字段填写规则。
- `AGENTS.md`：给 agent 使用的完整项目协作规则。

## 输出文件

`paper_processed/` 中的主要结果：

- `processed.rdf`：导入 Zotero 的 RDF 文件，持续追加，不会因新任务自动清空。
- `processing_notes.md`：处理备注，持续追加。
- `collection_assignments.csv`：分类分配清单，持续追加。
- `assign_collections.js`：导入 RDF 后，在 Zotero 中运行的分类分配脚本。

注意：`processed.rdf` 不写 Zotero collection。否则 Zotero 会新建同名分类，而不是合并到已有分类。

## Personal Rules 概要

当前个人规则主要覆盖以下文献类型和分类场景：

- `Clinical Study`：药物临床实验研究。
- `Spatial analysis`：空间组学数据预处理、生信分析、多模态联合分析等偏分析流程的方法文章。
- `Spatial benchmarking`：以空间组学实验方法、生信方法或模型方法 benchmark 为主旨的文章。
- `Spatial data & finding`：空间组学队列、数据资源或生物学发现文章，通常不以方法创新为主。
- `Spatial modeling`：空间组学相关建模、预测、预训练模型、大模型和下游任务模型文章。
- `Spatial wet tech`：空间组学实验技术、样本预处理或检测方法创新文章。
- `Target Discovery`：药物发现、靶点发现相关算法或应用案例。

`Spatial` 是父分类，不直接放文献。处理过的文章统一加 `Codexed` tag；其他 tag 不自创。

## 基本流程

1. 把待处理文献放入 `paper_to_be_processed/`。
2. 抽取/核验文献信息，并把 PDF 整理到 `paper_processed/files/`。
3. 生成临时中间表：

```powershell
python scripts/build_rdf.py --write-template
```

4. 填写 `paper_processed/.metadata_batch.csv`。
5. 运行：

```powershell
python scripts/build_rdf.py
```

脚本成功后会：

- 追加 `processed.rdf`
- 追加 `processing_notes.md`
- 追加 `collection_assignments.csv`
- 重写 `assign_collections.js`
- 删除临时中间表 `.metadata_batch.csv`
- 清理中间表中标记为已处理的 `paper_to_be_processed/` 输入

## Zotero 导入

1. 在 Zotero 中导入 `paper_processed/processed.rdf`。
2. 打开 `Tools -> Developer -> Run JavaScript`。
3. 勾选 `Run as async function`。
4. 粘贴并运行 `paper_processed/assign_collections.js` 的内容。

这一步会把导入条目加入已有 Zotero 分类。`Spatial` 子分类会用路径匹配，例如 `Spatial > Spatial wet tech`。
