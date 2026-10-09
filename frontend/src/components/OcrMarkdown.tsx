"use client";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";

// allow colspan/rowspan (the default schema may drop them)
const schema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    td: [...(defaultSchema.attributes?.td ?? []), "colSpan", "rowSpan", "align"],
    th: [...(defaultSchema.attributes?.th ?? []), "colSpan", "rowSpan", "align"],
  },
};

export default function OcrMarkdown({
  content,
  imageBaseUrl,
}: {
  content: string;
  imageBaseUrl?: string; // where your extracted crops are served from
}) {
  return (
    <div className="ocr-md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, [rehypeSanitize, schema]]} // order matters: raw first, sanitize last
        components={{
          img: ({ src, alt }) =>
            imageBaseUrl && typeof src === "string" ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={`${imageBaseUrl}/${src}`} alt={alt ?? ""} />
            ) : null, // relative "imgs/..." paths would 404 anyway
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
