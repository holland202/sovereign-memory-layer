// Reads one hex double per line from stdin; prints the port's exp(x) as hex, one per line.
import { readFileSync } from "node:fs";
import { bits, exp, fromBits } from "../src/pyfloat.ts";
const out: string[] = [];
for (const h of readFileSync(0, "utf8").split("\n")) if (h) out.push(bits(exp(fromBits(BigInt("0x" + h)))).toString(16).padStart(16, "0"));
process.stdout.write(out.join("\n") + "\n");
