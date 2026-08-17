// DO NOT EDIT: generated file; regenerate from declared inputs.
// Authored contract digest: sha256:908ed9b033faddecade3c0adb0d2ecc052243840e3b0b1b44419293e820ff430

export type JsonNumberNode = Readonly<{
  kind: "number";
  raw: string;
}>;

export type JsonArrayNode = Readonly<{
  kind: "array";
  items: ReadonlyArray<JsonNode>;
}>;

export type JsonObjectNode = Readonly<{
  kind: "object";
  members: ReadonlyArray<readonly [string, JsonNode]>;
}>;

export type JsonNode =
  | null
  | boolean
  | string
  | JsonNumberNode
  | JsonArrayNode
  | JsonObjectNode;

export function parseJsonResponse(text: string): JsonNode {
  return new JsonResponseParser(text).parse();
}

class JsonResponseParser {
  readonly #text: string;
  #index = 0;

  public constructor(text: string) {
    this.#text = text;
  }

  public parse(): JsonNode {
    this.#skipWhitespace();
    const value = this.#parseValue();
    this.#skipWhitespace();
    if (this.#index !== this.#text.length) this.#fail("unexpected trailing input");
    return value;
  }

  #parseValue(): JsonNode {
    const char = this.#text[this.#index];
    if (char === '"') return this.#parseString();
    if (char === "{") return this.#parseObject();
    if (char === "[") return this.#parseArray();
    if (char === "t") return this.#parseLiteral("true", true);
    if (char === "f") return this.#parseLiteral("false", false);
    if (char === "n") return this.#parseLiteral("null", null);
    if (char === "-" || isDigit(char)) return this.#parseNumber();
    return this.#fail("expected a JSON value");
  }

  #parseObject(): JsonObjectNode {
    this.#index += 1;
    this.#skipWhitespace();
    const members: Array<readonly [string, JsonNode]> = [];
    if (this.#take("}")) {
      return Object.freeze({kind: "object", members: Object.freeze(members)});
    }
    while (true) {
      if (this.#text[this.#index] !== '"') this.#fail("expected an object member name");
      const name = this.#parseString();
      this.#skipWhitespace();
      if (!this.#take(":")) this.#fail("expected ':' after an object member name");
      this.#skipWhitespace();
      members.push(Object.freeze([name, this.#parseValue()]));
      this.#skipWhitespace();
      if (this.#take("}")) {
        return Object.freeze({kind: "object", members: Object.freeze(members)});
      }
      if (!this.#take(",")) this.#fail("expected ',' or '}' in an object");
      this.#skipWhitespace();
    }
  }

  #parseArray(): JsonArrayNode {
    this.#index += 1;
    this.#skipWhitespace();
    const items: JsonNode[] = [];
    if (this.#take("]")) {
      return Object.freeze({kind: "array", items: Object.freeze(items)});
    }
    while (true) {
      items.push(this.#parseValue());
      this.#skipWhitespace();
      if (this.#take("]")) return Object.freeze({kind: "array", items: Object.freeze(items)});
      if (!this.#take(",")) this.#fail("expected ',' or ']' in an array");
      this.#skipWhitespace();
    }
  }

  #parseString(): string {
    const start = this.#index;
    this.#index += 1;
    while (this.#index < this.#text.length) {
      const char = this.#text[this.#index] ?? "";
      if (char === '"') {
        this.#index += 1;
        const decoded: unknown = JSON.parse(this.#text.slice(start, this.#index));
        if (typeof decoded !== "string") return this.#fail("invalid JSON string");
        return decoded;
      }
      if (char === "\\") {
        this.#index += 1;
        const escape = this.#text[this.#index] ?? "";
        if ('"\\/bfnrt'.includes(escape)) {
          this.#index += 1;
          continue;
        }
        if (escape !== "u") this.#fail("invalid JSON string escape");
        for (let offset = 1; offset <= 4; offset += 1) {
          if (!isHexDigit(this.#text[this.#index + offset])) {
            this.#fail("invalid JSON Unicode escape");
          }
        }
        this.#index += 5;
        continue;
      }
      if (char.charCodeAt(0) < 32) this.#fail("unescaped control character in JSON string");
      this.#index += 1;
    }
    return this.#fail("unterminated JSON string");
  }

  #parseNumber(): JsonNumberNode {
    const start = this.#index;
    if (this.#take("-") && this.#index === this.#text.length) {
      return this.#fail("incomplete JSON number");
    }
    if (this.#take("0")) {
      if (isDigit(this.#text[this.#index])) this.#fail("leading zero in JSON number");
    } else {
      const first = this.#text[this.#index];
      if (first === undefined || first < "1" || first > "9") {
        return this.#fail("invalid JSON number");
      }
      this.#index += 1;
      this.#takeDigits();
    }
    if (this.#take(".")) {
      if (!isDigit(this.#text[this.#index])) this.#fail("missing fraction digits");
      this.#takeDigits();
    }
    const exponent = this.#text[this.#index];
    if (exponent === "e" || exponent === "E") {
      this.#index += 1;
      const sign = this.#text[this.#index];
      if (sign === "+" || sign === "-") this.#index += 1;
      if (!isDigit(this.#text[this.#index])) this.#fail("missing exponent digits");
      this.#takeDigits();
    }
    return Object.freeze({kind: "number", raw: this.#text.slice(start, this.#index)});
  }

  #parseLiteral<Value extends boolean | null>(token: string, value: Value): Value {
    if (!this.#text.startsWith(token, this.#index)) this.#fail(`invalid token ${token}`);
    this.#index += token.length;
    return value;
  }

  #takeDigits(): void {
    while (isDigit(this.#text[this.#index])) this.#index += 1;
  }

  #take(expected: string): boolean {
    if (this.#text[this.#index] !== expected) return false;
    this.#index += 1;
    return true;
  }

  #skipWhitespace(): void {
    while (" \t\r\n".includes(this.#text[this.#index] ?? "x")) this.#index += 1;
  }

  #fail(reason: string): never {
    throw new SyntaxError(`Invalid ctower JSON response at offset ${this.#index}: ${reason}`);
  }
}

function isDigit(value: string | undefined): boolean {
  return value !== undefined && value >= "0" && value <= "9";
}

function isHexDigit(value: string | undefined): boolean {
  return (
    value !== undefined &&
    (isDigit(value) || value >= "A" && value <= "F" || value >= "a" && value <= "f")
  );
}
