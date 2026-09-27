// SPDX-License-Identifier: Apache-2.0
// WHATWG APIs exist in Node and supported browsers without importing Node types.
declare const TextEncoder: { new (): { encode(input: string): Uint8Array } };
declare const crypto: {
  subtle: { digest(algorithm: string, data: Uint8Array): Promise<ArrayBuffer> };
};

function scalars(value: string): void {
  for (let index = 0; index < value.length; index++) {
    const code = value.charCodeAt(index);
    if (code < 0xd800 || code > 0xdfff) continue;
    const next = value.charCodeAt(++index);
    if (code > 0xdbff || !(next >= 0xdc00 && next <= 0xdfff))
      throw new TypeError("Unpaired surrogate in semantic input");
  }
}

class SemanticReader {
  private at = 0;
  constructor(private readonly input: string) {}
  document(): unknown {
    const value = this.value(0);
    this.space();
    if (this.at !== this.input.length) throw new SyntaxError("Trailing semantic input");
    return value;
  }
  private space(): void {
    while (this.at < this.input.length && /[\x20\t\r\n]/.test(this.input[this.at]!)) this.at++;
  }
  private string(): string {
    const start = this.at++;
    let escaped = false;
    while (this.at < this.input.length) {
      const character = this.input[this.at++]!;
      if (!escaped && character === '"') {
        const result: unknown = JSON.parse(this.input.slice(start, this.at));
        if (typeof result !== "string") throw new SyntaxError("Expected string");
        scalars(result);
        return result;
      }
      if (!escaped && character === "\\") escaped = true;
      else escaped = false;
    }
    throw new SyntaxError("Unterminated semantic string");
  }
  private value(depth: number): unknown {
    this.space();
    const kind = this.input[this.at];
    if (kind === '"') return this.string();
    for (const [literal, value] of [
      ["true", true],
      ["false", false],
      ["null", null],
    ] as const) {
      if (this.input.startsWith(literal, this.at)) {
        this.at += literal.length;
        return value;
      }
    }
    if (kind !== "{" && kind !== "[")
      throw new SyntaxError("Numbers require exact canonical strings");
    if (depth >= 32) throw new SyntaxError("Semantic depth exceeds 32");
    this.at++;
    const close = kind === "{" ? "}" : "]";
    const object: Record<string, unknown> = Object.create(null) as Record<string, unknown>;
    const array: unknown[] = [];
    this.space();
    if (this.input[this.at] === close) {
      this.at++;
      return kind === "{" ? object : array;
    }
    for (;;) {
      this.space();
      if (kind === "{") {
        if (this.input[this.at] !== '"') throw new SyntaxError("Expected property name");
        const key = this.string();
        if (/[^\x00-\x7f]/.test(key) || Object.hasOwn(object, key))
          throw new SyntaxError("Duplicate or non-ASCII semantic property");
        this.space();
        if (this.input[this.at++] !== ":") throw new SyntaxError("Expected colon");
        object[key] = this.value(depth + 1);
      } else array.push(this.value(depth + 1));
      this.space();
      const delimiter = this.input[this.at++];
      if (delimiter === close) return kind === "{" ? object : array;
      if (delimiter !== ",") throw new SyntaxError("Expected comma");
    }
  }
}

/**
 * Registry04 JSON for a new owner profile with an explicit schemaVersion.
 * Exact numbers, UUIDs, hashes and bytes use the owner's canonical string adapters.
 * NFC is opt-in at RFC6901 string paths; existing content formats retain their own hash.
 */
export function canonicalSemanticJson(
  json: string,
  nfcPaths: ReadonlySet<string> = new Set(),
): string {
  scalars(json);
  if (new TextEncoder().encode(json).byteLength > 4 * 1024 * 1024)
    throw new RangeError("Semantic input exceeds 4 MiB");
  const root = new SemanticReader(json).document();
  if (
    root === null ||
    typeof root !== "object" ||
    Array.isArray(root) ||
    typeof (root as Record<string, unknown>).schemaVersion !== "string" ||
    !(root as Record<string, unknown>).schemaVersion
  )
    throw new TypeError("An explicit owner schemaVersion is required");
  const normalized = new Set<string>();
  function write(value: unknown, path: string): string {
    if (typeof value === "string") {
      if (nfcPaths.has(path)) {
        value = value.normalize("NFC");
        normalized.add(path);
      }
      return JSON.stringify(value);
    }
    if (value === null || typeof value === "boolean") return JSON.stringify(value);
    if (Array.isArray(value))
      return "[" + value.map((item, index) => write(item, path + "/" + index)).join(",") + "]";
    const object = value as Record<string, unknown>;
    return (
      "{" +
      Object.keys(object)
        .sort()
        .map(
          (key) =>
            JSON.stringify(key) +
            ":" +
            write(object[key], path + "/" + key.replaceAll("~", "~0").replaceAll("/", "~1")),
        )
        .join(",") +
      "}"
    );
  }
  const result = write(root, "");
  if (normalized.size !== nfcPaths.size)
    throw new TypeError("Every normalization path must identify a present string");
  return result;
}

/** SHA-256 over canonical UTF-8, returned as lower-case hexadecimal. */
export async function canonicalSemanticHash(
  json: string,
  nfcPaths?: ReadonlySet<string>,
): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalSemanticJson(json, nfcPaths));
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return Array.from(digest, (value) => value.toString(16).padStart(2, "0")).join("");
}
