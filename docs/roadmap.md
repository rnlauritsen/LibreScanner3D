# Roadmap / design ideas (nothing here is implemented yet)

## 1. Tracking that knows when it is lost
Today the pipeline tracks a hand-turned base with one fixed axis. The end goal is hand-held scanning that is honest about its own tracking.

Per frame, measure (a) what fraction of the view matches the already-scanned model and (b) the leftover error. Use these as a gate.

States:
1. **Tracking** - live camera view next to the growing model; points are added to the model.
2. **Lost** - stop adding to the model. Show a "tracking lost" message, bring up the overlay (below), and mark the area to return to in **orange** (already-scanned area in **blue**, unscanned gaps in a third colour). New frames go into a short holding buffer.
3. **Found** - when the live view matches the model for about a second, say "tracking re-aligned" and hide the overlay.
4. **Resume** - merge the buffered frames and continue normally.

Overlay: render the model from the last good position, at the true size and distance, semi-transparently over the live camera view, so the user moves until the ghost image fits the live view. Show it only in the *lost* state (it hides what the scanner sees otherwise); allow a key press to show it on demand.

Other design points:
* Track against a recent local patch of the model (cheaper, robust against old errors); use the whole model only to detect drift when the user returns to an old area.
* Keep holding-buffer pieces short. A piece is only as good as the frame-to-frame matching inside it; discard one that never lines up.
* Smooth, round or featureless areas defeat shape-based tracking. Remedies: scanning spray, stickers, dots, a turntable mat with a non-repeating pattern (printed patterns are visible to the stripe camera; rotationally symmetric rings are not enough to give the angle).

## 2. Stitching several scans into one model
Use when an area keeps failing, or the object cannot be scanned from all sides in one go (e.g. a box: outside, then its bottom).

Method: find a rough alignment between two scans from shape features where they overlap, then refine with ICP (already used in the tracker).

**Guidance the software should give the user**
* Do at least **3 scans, with the object resting on 3 different faces**. Each pair of scans should share an overlapping area; with three, the overlaps form a chain that can be checked for consistency, which two scans cannot.
* In each scan, also scan a band of the sides/edges that the neighbouring scan sees, so there is overlap to match.

**Risks and safeguards**
* Plain or symmetric objects (a box) can match in more than one orientation, e.g. flipped. Show the proposed alignment with a confidence score and the runner-up, and let the user pick.
* Manual fallback: the user clicks three matching points on each scan to give the starting alignment; software refines.
* Do not merge automatically when confidence is low.
