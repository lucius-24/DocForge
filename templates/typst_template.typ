// Pandoc Typst template (minimal) to improve CJK and TOC appearance
// This template is intentionally minimal and safe.

#set page(margin: 2cm)
#set text(font: "Microsoft YaHei")

// Use dotted leaders in table of contents and increase depth
#show outline: set(
  indent: 1em,
  fill: dot
)

// Space between headings and body
#show heading: it => block(
  spacing: (before: 12pt, after: 6pt),
  it,
)

// Page break before level-1 headings
#show heading.where(level: 1): it => [
  #pagebreak()
  #it
]

// Body placeholder replaced by Pandoc
$body$

