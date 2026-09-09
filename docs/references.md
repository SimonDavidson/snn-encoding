# References

Primary sources for factual claims made in `docs/proposal_v2.md` and
`docs/validation_protocol.md`.

This file exists because §2 of the validation protocol requires that "any
factual claim that matters — a published figure, a tool's behaviour, a
convention — must be traced to a primary source before it enters the paper",
and until now there was nowhere in the repository for a source to be recorded.
The proposal cites inline by surname only. A claim cannot be traced to a
source the repository does not hold.

**Read** means someone in this project has read the paper in full and the
claims attributed to it here were checked against it. **Not read** means the
description in our documents came from abstracts, citation records or recall,
and is subject to §2's warning. Say which; the distinction is the whole point.

**PDFs are not committed.** They are published under licence and this
repository is public — the same reason `data/` is gitignored. Keep local
copies under `papers/`, which `.gitignore` excludes.

---

## Spiketrum (E7)

**[Tang2025]** Huajin Tang, Pengjie Gu, Jayawan Wijekoon, MHD Anas Alsakkal,
Ziming Wang, Jiangrong Shen, Rui Yan and Gang Pan, "Neuromorphic Auditory
Perception by Neural Spiketrum", *IEEE Transactions on Emerging Topics in
Computational Intelligence*, vol. 9, no. 1, pp. 292–303, February 2025.
DOI [10.1109/TETCI.2024.3419711](https://doi.org/10.1109/TETCI.2024.3419711).
Received 15 August 2023; accepted 25 May 2024; published 18 September 2024.

**Status: read in full, 2026-09-09, implementation session.** This is the
TETCI article `docs/proposal_v2.md` §5.7 names as the first of three sources
to obtain. What it establishes, and where §5.7 is wrong, is recorded in Q41.

Corresponding author Huajin Tang, Zhejiang University. The Manchester authors
are Jayawan Wijekoon (`jayawan.wijekoon@manchester.ac.uk`) and MHD Anas
Alsakkal (`mhdanas.alsakkal@manchester.ac.uk`), third and fourth of eight.

Two further sources §5.7 names are still outstanding: a TCSI article on the
FPGA cochlea, and an evaluation paper on the encoder. Note that [Tang2025]
cites **no** paper authored by Wijekoon or Alsakkal, and describes the FPGA
cochlea itself in its §V — so whether those two exist as §5.7 describes them
is not settled by having read this one. §5.7's list was itself assembled from
citation records.

## Cited by [Tang2025] and relevant to this study

- **[Cramer2020]** B. Cramer, Y. Stradmann, J. Schemmel and F. Zenke, "The
  Heidelberg spiking data sets for the systematic evaluation of spiking neural
  networks" — reference [72] of [Tang2025]. This is SHD, our reference point
  R1. Not read.
- **[Krstulovic2006]** S. Krstulovic and R. Gribonval, "MPTK: Matching pursuit
  made ..." — reference [54] of [Tang2025], cited there as the basis for the
  claim that the number of spike codes is controllable. An existing
  open-source matching-pursuit toolkit, and therefore relevant to whether E7's
  *family* can be run without reimplementing Spiketrum itself. Not read.
- **[Panayotov2015]** LibriSpeech — reference [76] of [Tang2025]. The
  proposal's fallback corpus if the TIMIT licence (O2) cannot be obtained.
  Not read.
