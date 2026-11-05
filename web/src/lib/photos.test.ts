import { describe, expect, it } from "vitest";
import { acceptPhoto, initials, titleCandidates, wikiTitle } from "./photos";

describe("initials", () => {
  it("uses first and last name", () => expect(initials("Jon Ossoff")).toBe("JO"));
  it("drops suffixes and middle names", () =>
    expect(initials("Vicente A. Ada Jr.")).toBe("VA"));
  it("handles one word and empty", () => {
    expect(initials("Cher")).toBe("C");
    expect(initials("  ")).toBe("?");
  });
});

describe("acceptPhoto", () => {
  const thumb = { source: "https://upload.wikimedia.org/x.jpg" };
  it("accepts a politician page with a thumbnail", () =>
    expect(
      acceptPhoto({ type: "standard", description: "American politician", thumbnail: thumb })
    ).toBe(thumb.source));
  it("rejects non-politicians, disambiguation pages and missing thumbnails", () => {
    expect(acceptPhoto({ type: "standard", description: "American footballer", thumbnail: thumb })).toBeNull();
    expect(acceptPhoto({ type: "disambiguation", description: "politician", thumbnail: thumb })).toBeNull();
    expect(acceptPhoto({ type: "standard", description: "American politician" })).toBeNull();
    expect(acceptPhoto(null)).toBeNull();
  });
});

it("builds Wikipedia titles", () => expect(wikiTitle(" Jon  Ossoff ")).toBe("Jon_Ossoff"));

it("tries state-disambiguated titles after the plain name", () => {
  expect(titleCandidates("Mike Collins", "GA")).toEqual([
    "Mike Collins",
    "Mike Collins (Georgia politician)",
    "Mike Collins (politician)",
    "Mike Collins (American politician)",
    "Mike Collins (U.S. senator)",
  ]);
  expect(titleCandidates("Jane Doe", null)).toHaveLength(4);
});
