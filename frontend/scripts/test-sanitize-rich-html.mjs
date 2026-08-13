import assert from "node:assert/strict";
import { sanitizeRichHtml } from "../lib/sanitize-rich-html.ts";

const dangerous = '<p onclick="steal()">Bonjour<script>alert(1)</script><a href="javascript:alert(2)">lien</a></p>';
const sanitized = sanitizeRichHtml(dangerous);

assert.equal(sanitized, '<p>Bonjour<a rel="noopener noreferrer">lien</a></p>');
assert.doesNotMatch(sanitized, /script|onclick|javascript:/i);
