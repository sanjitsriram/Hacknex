import { z } from "zod";
import { parse } from "node-html-parser";

export const LabResult = z.object({
  section: z.string().nullable(),
  test: z.string(),
  value: z.object({
    raw: z.string(),
    kind: z.enum(["text", "number", "range"]),
    min: z.number().optional(),
    max: z.number().optional(),
  }),
  unit: z.string().nullable(),
  referenceRange: z.string().nullable(),
  source: z.object({ blockId: z.string(), confidence: z.number() }),
});

export const LabReport = z.object({
  report: z.object({
    type: z.string().nullable(),
    department: z.string().nullable(),
    specimen: z.string().nullable(),
  }),
  patient: z.object({
    salutation: z.string().nullable(),
    name: z.string().nullable(),
    age: z.number().nullable(),
    ageUnit: z.string().nullable(),
    sex: z.string().nullable(),
    mrNo: z.string().nullable(),
  }),
  ids: z.object({ labId: z.string().nullable(), visitNo: z.string().nullable() }),
  dates: z.object({
    test: z.string().nullable(),
    sample: z.string().nullable(),
    report: z.string().nullable(),
  }),
  referralDoctor: z.string().nullable(),
  results: z.array(LabResult),
  review: z.object({ status: z.literal("unverified"), warnings: z.array(z.string()) }),
});
export type LabReport = z.infer<typeof LabReport>;

const toISO = (d: string) => {
  const m = d.match(/^(\d{2})-(\d{2})-(\d{4})$/);
  return m ? `${m[3]}-${m[2]}-${m[1]}` : null;
};

function parseValue(raw: string) {
  const r = raw.trim();
  const range = r.match(/^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$/);
  if (range) return { raw: r, kind: "range" as const, min: +range[1], max: +range[2] };
  if (/^\d+(\.\d+)?$/.test(r)) return { raw: r, kind: "number" as const, min: +r, max: +r };
  return { raw: r, kind: "text" as const };
}

function parseTable(block: any): z.infer<typeof LabResult>[] {
  const rows = parse(block.content).querySelectorAll("tr");
  const out: z.infer<typeof LabResult>[] = [];
  let section: string | null = null;

  rows.slice(1).forEach((tr) => {            // slice(1) skips the header row
    const [name, result, unit, ref] = tr
      .querySelectorAll("td")
      .map((td) => td.text.trim());
    if (!name) return;
    if (!result && !unit && !ref) { section = name; return; } // group row
    out.push({
      section,
      test: name,
      value: parseValue(result),
      unit: unit || null,
      referenceRange: ref || null,
      source: { blockId: block.block_id, confidence: block.confidence },
    });
  });
  return out;
}

export function parseLabReport(run: any): LabReport {
  const blocks: any[] = run.pages.flatMap((p: any) => p.blocks);
  const kv: Record<string, string> = {};
  let specimen: string | null = null;

  for (const b of blocks.filter((b: any) => b.block_type === "text")) {
    for (const line of String(b.content).split("\n")) {
      const m = line.match(/^([A-Za-z\/ ]+?):\s*(.+)$/);
      if (m) kv[m[1].trim().toLowerCase()] = m[2].trim();
      const s = line.match(/^Specimen\s+(.+)$/i);
      if (s) specimen = s[1];
    }
  }

  const nameMatch = kv["patient name"]?.match(/^(Mr|Mrs|Ms|Miss|Dr)\.?\s+(.+)$/i);
  const ageSex = kv["age/sex"]?.match(/^(\d+)\s*([YMD])\s*\/\s*([MF])$/i);
  const titles = blocks.filter((b: any) => b.block_type === "paragraph_title").map((b: any) => b.content);
  const tableBlock = blocks.find((b: any) => b.block_type === "table");

  const warnings: string[] = [];
  const results = tableBlock ? parseTable(tableBlock) : [];
  if (!tableBlock) warnings.push("no table block found");
  if (tableBlock && tableBlock.confidence < 0.5) warnings.push("low table confidence, review needed");
  if (results.every((r) => !r.unit && !r.referenceRange)) warnings.push("units/reference ranges missing in source");

  return LabReport.parse({
    report: { type: titles[0] ?? null, department: titles[1] ?? null, specimen },
    patient: {
      salutation: nameMatch ? nameMatch[1] + "." : null,
      name: nameMatch ? nameMatch[2] : kv["patient name"] ?? null,
      age: ageSex ? +ageSex[1] : null,
      ageUnit: ageSex ? ageSex[2].toUpperCase() : null,
      sex: ageSex ? ageSex[3].toUpperCase() : null,
      mrNo: kv["mr no"] ?? null,
    },
    ids: { labId: kv["lab id no"] ?? null, visitNo: kv["visit no"] ?? null },
    dates: {
      test: kv["test date"] ? toISO(kv["test date"]) : null,
      sample: kv["sample date"] ? toISO(kv["sample date"]) : null,
      report: kv["report date"] ? toISO(kv["report date"]) : null,
    },
    referralDoctor: kv["referral doctor"] ?? null,
    results,
    review: { status: "unverified", warnings },
  });
}
