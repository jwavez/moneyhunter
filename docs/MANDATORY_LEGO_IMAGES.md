# Mandatory LEGO product photos

## Actual incident evidence

At investigation on 7 November 2026 the latest normal live scan was run42398914257, exported17:59:01 GMT, revision29d27ee (BEFORE PR13). Its Lucky Cat acquisition was the £24.99 offer https://www.ebay.co.uk/itm/317761343050 . The latest export on36cf02f was18:00:59 GMT **no-send**, not a replacement normal Discord post. Therefore the screenshot's17:58:45 competitor-observation timestamp was not proof of a new post or of the new renderer running. PR13 restored image metadata but did not edit old posts or enforce a mandatory photo gate. It was not sufficient to promise every future product card would be image-backed.

The exact40813 reference is https://www.hotukdeals.com/deals/lego-lucky-cat-40813-5025155 with source photo https://images.hotukdeals.com/threads/raw/uzv4N/5025155_1/re/300x300/qt/55/5025155_1.jpg . The live photo returned200, image/jpeg, image signature, and was visually checked as the LEGO40813 Lucky Cat box. The final Python webhook serializer was exercised with all four real40813 research rows without posting.

## Enforcement

- Python scan checks real LEGO photos using approved HTTPS image-CDN hosts, no redirects/credentials, status200, image MIME plus magic signature, and a maximum4096-byte prefix read with3-second timeout. At most32 uncached checks per scan; positive cache20minutes, negative5minutes. Permission denial pauses that image host until explicitly reviewed; no alternate/proxy bypass.
- Preserve the supplied URL; never blindly rewrite a validated URL afterwards. A HUKD300px variant may be tried before its source150px counterpart, but only a working checked URL is published. An own photograph wins; a missing/broken original can use only an exact set/name/condition-matched reference from validated feed rows or official Browse evidence, clearly labelled not proof of listing condition. No invented image addresses for arbitrary products.
- Missing, broken, expired or budget-held photos remain pending with original candidates retained for retry. They are excluded from every automatic LEGO product route, including grouped trending/near-miss posts. Their posted acknowledgement keys are not added. No old seen keys are reset.
- The final shared webhook serializer independently rejects image-free, altered or expired LEGO image payloads, even if routing is bypassed. Internal verification metadata is removed before Discord JSON is sent.
- Export image provenance, verification state/expiry, pending counts. A no-send export also contains `lego_publication_previews`, using exactly the same final serializer as the real Python webhook sender, not merely the Worker UI builder. This does not send or acknowledge anything.
- Worker signed interaction responses independently verify the selected photo (at most two known candidate URLs;900ms timeout each), use the existing edge Cache API rather than per-photo KV writes, reject redirects/non-images and hold the product card if no working image exists. Research, category/deal, trade-plan and price-check product cards pass the same final guard. Only denied-host pause uses existing KV persistence. Generic menus, moderation and aggregate scan statistics are not product cards.

## Limits and unchanged behaviour

No spending cap, fee, profit threshold, category acquisition, seen acknowledgement or live schedule policy is changed. External CDN failure after a check or Discord rendering settings cannot be prevented forever. The enforceable promise is that we do not knowingly publish a LEGO product card without a recently checked working image; we hold it instead. No manually sent test, old-message edit, duplicate repost or forced live test is required.
