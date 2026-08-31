import assert from "node:assert/strict";
import { partialPaymentCents } from "../lib/invoice-partial-payment.ts";

for (const [value, expected] of [["396", 39600], ["396,00", 39600], ["396.00", 39600], ["1 096,00", 109600]]) {
  assert.equal(partialPaymentCents(value), expected);
}
for (const value of ["", "-396", "NaN", "Infinity", "396.001", "3e2", "1,2.3", "abc"]) {
  assert.equal(partialPaymentCents(value), null, value);
}
assert.equal(partialPaymentCents("1096") - partialPaymentCents("396"), 70000);
console.log("Partial-payment money parsing: OK");
