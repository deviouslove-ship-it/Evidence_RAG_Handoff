**Language / Ngôn ngữ:** [Tiếng Việt](citation-contract.md) · English

English counterpart of `docs/citation-contract.md`. The Vietnamese file is the original.

# Citation contract

Every evidence item must have a stable identity and be traceable back to:

1. an immutable `document_version_id`;
2. `document_nodes.id`;
3. `source_spans.id`, page, original offset/length, and quads;
4. the SHA-256 of the original PDF file;
5. `as_of_date` and the reviewed effectivity (hiệu lực) status;
6. the principal's permissions at the time the citation is opened.

The quote is always hydrated from `document_nodes.text_original`. The LLM does not supply the quote, the node ID, or the page number. When bbox, CropBox, or rotation is uncertain, the viewer only opens the page and displays the quote. It must never highlight the wrong position.

When an old citation is opened, the server rechecks the ACL and the policy. If the permission has been revoked, it returns `403`. It does not replay cached content.
