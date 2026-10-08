import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'HackNex — Every word, accounted for.', description: 'An evidence-first workspace for reviewing difficult handwriting.' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
