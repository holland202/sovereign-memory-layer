// Python's exception classes as the store raises them; the CLI reports the first matching name in the
// same order as tools/py_cli.py.
export class RuntimeError extends Error {}
export class ValueError extends Error {}
export class OSError extends Error {}
export class CapacityError extends RuntimeError {}
export class IntegrityError extends RuntimeError {}
export class LockError extends IntegrityError {}
export class ReentrancyError extends RuntimeError {}
export class CommitUncertain extends RuntimeError {}

export function classify(e: unknown): string {
  const order: [string, Function][] = [
    ["ReentrancyError", ReentrancyError], ["CommitUncertain", CommitUncertain], ["CapacityError", CapacityError],
    ["IntegrityError", IntegrityError], ["ValueError", ValueError], ["OSError", OSError], ["RuntimeError", RuntimeError],
  ];
  for (const [n, c] of order) if (e instanceof c) return n;
  return e instanceof Error ? e.constructor.name : "Exception";
}

/** Run a filesystem call; Node's errors become OSError, as Python's do. */
export function os<T>(f: () => T): T {
  try {
    return f();
  } catch (e) {
    if (e instanceof Error && "code" in e) throw new OSError(e.message);
    throw e;
  }
}
