import { NextResponse } from 'next/server';
import { parseLabReport } from '@/lib/parseLabReport';

export async function POST(request: Request) {
  try {
    const parsingRun = await request.json();
    const result = parseLabReport(parsingRun);
    return NextResponse.json(result);
  } catch (error: any) {
    return NextResponse.json({ error: error.message || 'Failed to parse lab report' }, { status: 400 });
  }
}
