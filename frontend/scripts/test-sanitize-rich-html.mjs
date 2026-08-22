import assert from "node:assert/strict";
import { sanitizeExternalCourseContentHtml, sanitizeRichHtml } from "../lib/sanitize-rich-html.ts";

const dangerous = '<p onclick="steal()">Bonjour<script>alert(1)</script><a href="javascript:alert(2)">lien</a></p>';
const sanitized = sanitizeRichHtml(dangerous);

assert.equal(sanitized, '<p>Bonjour<a rel="noopener noreferrer">lien</a></p>');
assert.doesNotMatch(sanitized, /script|onclick|javascript:/i);

const embeddedLesson = sanitizeExternalCourseContentHtml(`
  <iframe src="http://www.cloudlearning.fr/demo" onclick="steal()"></iframe>
  <iframe src="https://puzzel.org/fr/crossword/play?p=-example"></iframe>
  <iframe src="https://www.canva.com/design/example/view"></iframe>
  <iframe src="https://evil.example/embed"></iframe>
  <img src="http://piano-academie.com/wp-content/uploads/lesson.png" alt="Partition" onerror="steal()">
  <img src="https://evil.example/tracker.png">
`);

assert.match(embeddedLesson, /https:\/\/www\.cloudlearning\.fr\/demo/);
assert.match(embeddedLesson, /https:\/\/puzzel\.org\/fr\/crossword\/play\?p=-example/);
assert.match(embeddedLesson, /https:\/\/www\.canva\.com\/design\/example\/view/);
assert.match(embeddedLesson, /https:\/\/piano-academie\.com\/wp-content\/uploads\/lesson\.png/);
assert.match(embeddedLesson, /sandbox="allow-forms allow-popups allow-presentation allow-same-origin allow-scripts"/);
assert.match(embeddedLesson, /loading="lazy"/);
assert.doesNotMatch(embeddedLesson, /evil\.example|onclick|onerror/i);

const genericPreview = sanitizeRichHtml('<iframe src="https://www.cloudlearning.fr/demo"></iframe><img src="https://piano-academie.com/demo.png">');
assert.equal(genericPreview, "");
