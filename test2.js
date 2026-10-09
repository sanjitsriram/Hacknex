const { parse } = require("node-html-parser");

const html = "<table border=1 style='margin: auto; word-wrap: break-word;'><tr><td style='text-align: center; word-wrap: break-word;'>Test Description</td><td style='text-align: center; word-wrap: break-word;'>Result</td><td style='text-align: center; word-wrap: break-word;'>Units</td><td style='text-align: center; word-wrap: break-word;'>Reference Range</td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Urine Routine Analysis</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr><tr><td style='text-align: center; word-wrap: break-word;'>Colour</td><td style='text-align: center; word-wrap: break-word;'>Pale Yellow</td><td style='text-align: center; word-wrap: break-word;'></td><td style='text-align: center; word-wrap: break-word;'></td></tr></table>";

const root = parse(html);
const rows = root.querySelectorAll("tr");
console.log(rows.length); // 3

rows.slice(1).forEach(tr => {
    const tds = tr.querySelectorAll("td");
    console.log(tds.map(td => td.text.trim()));
});
