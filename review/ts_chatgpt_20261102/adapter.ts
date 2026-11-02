// Review-only access to the frozen port's exported helpers; production source is unchanged.
import { createInterface } from "node:readline";
import { canonical, parseString, type Value } from "../../ts/src/json.ts";
import { classify } from "../../ts/src/errors.ts";
import { hashEmbedding } from "../../ts/src/store.ts";
import { bits, exp, fromBits } from "../../ts/src/pyfloat.ts";
const rl = createInterface({ input: process.stdin, terminal: false });
rl.on("line", line => {
  let result: unknown;
  try {
    const op = parseString(line) as Map<string, Value>;
    let value: string;
    if (op.get("action") === "canonical") value = canonical(op.get("value")!).toString("hex");
    else if (op.get("action") === "hash") value = canonical(hashEmbedding(op.get("value"))).toString("hex");
    else if (op.get("action") === "exp") value = bits(exp(fromBits(BigInt("0x" + op.get("value"))))).toString(16).padStart(16, "0");
    else throw new Error("unknown adapter action");
    result = { ok: true, result: value };
  } catch (error) { result = { ok: false, error: classify(error) }; }
  process.stdout.write(JSON.stringify(result) + "\n");
});
