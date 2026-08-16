#!/usr/bin/env python3
"""Generate a HyperFrames composition from a shot list.

This is the renderer half of the sheet -> video path. It exists because the
first hand-authored section had 4 shots where the reference editor cuts about
24, and hand-writing 26 shots of HTML is not maintainable.

WHAT THE SHOT LIST ENCODES, and why each field is there:

  t0            cut time. These come from RESOLVED WORD ANCHORS, never typed
                seconds, so a re-recorded VO re-syncs the whole edit.
  ground        'plate:<name>' or 'white'. Measured from M Simplified: story
                beats live on a plate the editor owns, spec beats bleed the
                subject on white.
  asset         which cutout. The reference gets ~10 treatments out of one
                artwork; a single asset reused at one angle is what made the
                first attempt read as a sticker.
  from_/to      transform at shot start and end: [x, y, scale] in frame
                fractions. Animated with transform only - Chrome snaps layout
                to whole device pixels and emits duplicate frames on slow
                moves, which measures as dead air.
  pop           keyword text, 1-4 words, anchored to its spoken word.

MOTION SHAPE, and a correction. This file used to say that the reference's
26.4% average frame change came from MANY HARD CUTS between held framings, and
that the generator should therefore target shot COUNT. That was inferred from
an aggregate and never measured, and it was wrong.

Measured by frame differencing at 10 fps over 130 seconds: the reference cuts
15.2 times a minute against this generator's 18.4, and holds one framing for as
long as 23.1 seconds against a longest hold of 6.1. He cuts LESS. The motion
comes from events INSIDE a held frame - a screen turns on, static resolves, an
image appears, it multiplies, the camera pulls back - and reproducing his
number by cutting 26 times is what made the output read as a machine.

So the shot list this file renders is now produced by build_scenes.py, which
targets scenes and the events inside them. This file stays the renderer: it
turns whatever it is given into HyperFrames HTML, and it no longer has an
opinion about how many shots there should be.
"""
import argparse, json, os


ICON_SVG = {
    # Black stick figure. Both references use it as SCALE and as victim, and it
    # reacts - it is never a static pictogram sitting on the frame.
    "figure": ('<g><circle cx="0" cy="-96" r="19" fill="{c}"/>'
               '<line x1="0" y1="-77" x2="0" y2="-26" stroke="{c}" stroke-width="12"/>'
               '<line x1="0" y1="-64" x2="-26" y2="-38" stroke="{c}" stroke-width="11"/>'
               '<line x1="0" y1="-64" x2="26" y2="-38" stroke="{c}" stroke-width="11"/>'
               '<line x1="0" y1="-26" x2="-20" y2="10" stroke="{c}" stroke-width="11"/>'
               '<line x1="0" y1="-26" x2="20" y2="10" stroke="{c}" stroke-width="11"/></g>'),
    # Red annotation arrow. Red is RESERVED for annotation in both references.
    "arrow": ('<g><line x1="0" y1="0" x2="-150" y2="66" stroke="#D62020" stroke-width="13"/>'
              '<polygon points="-150,66 -104,44 -108,84" fill="#D62020"/></g>'),
    # Red X over a silhouette: danger, death or absence.
    "redx": ('<g><line x1="-52" y1="-52" x2="52" y2="52" stroke="#D62020" stroke-width="16"/>'
             '<line x1="52" y1="-52" x2="-52" y2="52" stroke="#D62020" stroke-width="16"/></g>'),
}

HEAD = '''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <script src="public/js/gsap.min.js"></script>
    <style>
      /* Vu's actual face, confirmed by pixel comparison against his publish cut. */
      @font-face { font-family:"HouseTitle"; src:url("public/fonts/comic-sans-ms-bold.ttf") format("truetype"); font-display:block; }
      * { margin:0; padding:0; box-sizing:border-box; }
      html, body { width:1920px; height:1080px; overflow:hidden; background:#000; }
      .stage { position:absolute; inset:0; overflow:hidden; background:#000; }
      .stage.white { background:#FFFFFF; }
      .plate { position:absolute; left:0; top:0; width:1920px; height:1080px;
               transform-origin:50% 50%; will-change:transform; }
      .cut { position:absolute; left:0; top:0; transform-origin:50% 50%;
             will-change:transform; }
      /* Contact shadow. A cutout with no shadow reads as a sticker pasted on. */
      .cut.grounded { filter: drop-shadow(0 18px 26px rgba(0,0,0,.55)); }

      /* Persistent creature name. Fill is CONTEXTUAL, measured from Vu:
         black with no stroke on white canvas, white with a dark stroke plus an
         outer white highlight over a plate. */
      .title { position:absolute; left:0; top:34px; width:1920px; text-align:center;
               font-family:"HouseTitle",sans-serif; font-size:96px;
               will-change:transform,opacity;
               color:#FFFFFF; -webkit-text-stroke:8px #111111; paint-order:stroke fill;
               text-shadow: 5px 0 0 #FFF,-5px 0 0 #FFF,0 5px 0 #FFF,0 -5px 0 #FFF,
                            4px 4px 0 #FFF,-4px 4px 0 #FFF,4px -4px 0 #FFF,-4px -4px 0 #FFF; }
      .title.onWhite { color:#111111; -webkit-text-stroke-width:0; text-shadow:none; }

      /* Pops sized to the reference: big, not captions. */
      .pop { position:absolute; left:0; width:1920px; text-align:center;
             font-family:"HouseTitle",sans-serif; font-size:96px; white-space:nowrap;
             will-change:transform,opacity;
             color:#FFFFFF; -webkit-text-stroke:8px #111111; paint-order:stroke fill;
             text-shadow: 5px 0 0 #FFF,-5px 0 0 #FFF,0 5px 0 #FFF,0 -5px 0 #FFF,
                          4px 4px 0 #FFF,-4px 4px 0 #FFF,4px -4px 0 #FFF,-4px -4px 0 #FFF; }
      .pop.side { width:900px; text-align:left; left:150px; }
      .pop.ink { color:#111111; -webkit-text-stroke-width:0; text-shadow:none; }
      .pop.red { color:#D62020; }
      svg.ov { position:absolute; inset:0; width:1920px; height:1080px; overflow:visible; }

      /* BOXED INSERT. The reference's answer to a line that names a thing:
         the thing appears in a bordered box over the scene, and when a line
         names two things there are two boxes side by side. This is the layer
         that lets a framing be HELD for twenty seconds and still change every
         couple of seconds, which is the whole point. */
      .box { position:absolute; transform-origin:50% 50%; will-change:transform,opacity;
             border:9px solid #111111; background:#FFFFFF; overflow:hidden;
             box-shadow:0 22px 40px rgba(0,0,0,.55); }
      .box.on-white { box-shadow:0 14px 26px rgba(0,0,0,.28); }
      .box > img { width:100%; height:100%; object-fit:cover; display:block; }
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{dur}"
         data-width="1920" data-height="1080" data-fps="30">

      <audio id="vo" class="clip" data-start="0" data-duration="{dur}" src="public/{vo}"></audio>
'''

TAIL = '''    </div>

    <script>
      window.__timelines = window.__timelines || {};
      const tl = gsap.timeline({ paused: true });
      gsap.set(".pop", {autoAlpha:0});
{body}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
'''


def build(sheet, out_html):
    shots = sheet["shots"]
    dur = sheet["duration"]
    # plain replace, not .format(): the CSS in HEAD is full of braces
    html = [HEAD.replace("{dur}", str(dur)).replace("{vo}", sheet["vo"])]
    js = []

    for n, s in enumerate(shots, 1):
        sid = f"s{n:02d}"
        t0, t1 = s["t0"], s["t1"]
        length = round(t1 - t0, 3)
        white = s["ground"] == "white"
        html.append(f'      <div id="{sid}" class="clip stage{" white" if white else ""}" '
                    f'data-start="{t0}" data-duration="{length}" data-track-index="1">')
        if not white:
            html.append(f'        <img id="{sid}p" class="plate" src="public/{s["ground"].split(":",1)[1]}" />')
        if s.get("asset"):
            gnd = "" if white else " grounded"
            html.append(f'        <img id="{sid}c" class="cut{gnd}" src="public/{s["asset"]}" />')
        # CREATURE LAYERS. The reference's held sequences are alive because
        # things ARRIVE inside them: a screen lights, an image appears, it
        # duplicates. A cutout that is simply present from the first frame of a
        # twenty second shot gives five identical frames, which is what the
        # first scene-based cut produced. So every creature part named by the
        # narration enters on its own spoken word.
        for j, cl in enumerate(s.get("layers", []), 1):
            lid = f"{sid}L{j}"
            gnd = "" if white else " grounded"
            html.append(f'        <img id="{lid}" class="cut{gnd}" '
                        f'src="public/{cl["src"]}" />')
            x, y, sc = cl["x"], cl["y"], cl["scale"]
            js.append(f'      gsap.set("#{lid}", {{xPercent:-50, yPercent:-50, '
                      f'x:{round(x*1920)}, y:{round(y*1080)}, scale:{sc}, '
                      f'autoAlpha:{1 if cl.get("carried") else 0}}});')
            # enters from the side the neck runs to, so it reads as the
            # creature extending into frame rather than a layer switching on
            dx = -260 if cl.get("from_left") else 260
            if cl.get("carried"):
                js.append(f'      tl.to("#{lid}", {{scale:{round(sc*1.07,3)}, '
                          f'duration:{max(0.6, round(t1-t0,3))}, ease:"none"}}, {t0});')
                continue
            js.append(f'      tl.fromTo("#{lid}", {{autoAlpha:0, x:"+={dx}", '
                      f'scale:{round(sc*0.92,3)}}}, {{autoAlpha:1, x:{round(x*1920)}, '
                      f'scale:{sc}, duration:0.44, ease:"power3.out"}}, {cl["at"]});')
            js.append(f'      tl.to("#{lid}", {{scale:{round(sc*1.07,3)}, '
                      f'duration:{max(0.6, round(t1-cl["at"],3))}, ease:"none"}}, {cl["at"]});')

        # Inserts arrive one at a time inside the held framing. Each one is an
        # EVENT: before its `at` it is not there, after it is. A scene with
        # three inserts changes three times without a single cut.
        for j, bx in enumerate(s.get("inserts", []), 1):
            bid = f"{sid}b{j}"
            w, h = round(bx["w"] * 1920), round(bx.get("h", bx["w"] * 0.62) * 1080)
            x, y = round(bx["x"] * 1920 - w / 2), round(bx["y"] * 1080 - h / 2)
            cls = "box on-white" if white else "box"
            html.append(f'        <div id="{bid}" class="{cls}" style="left:{x}px;'
                        f'top:{y}px;width:{w}px;height:{h}px;">'
                        f'<img src="public/{bx["src"]}" /></div>')
            at = bx.get("at", t0)
            if bx.get("carried"):
                # already on screen before this cut: appear instantly, no
                # re-entrance, or every punch restages the same box
                js.append(f'      gsap.set("#{bid}", {{autoAlpha:1, scale:1, '
                          f'rotation:{bx.get("tilt", 0)}}});')
            else:
                js.append(f'      gsap.set("#{bid}", {{autoAlpha:0}});')
                js.append(f'      tl.fromTo("#{bid}", {{autoAlpha:0, scale:0.86, '
                          f'rotation:{bx.get("tilt", 0)}}}, {{autoAlpha:1, scale:1, '
                          f'duration:0.26, ease:"back.out(1.6)"}}, {at});')
            # A box that stays perfectly still for the rest of a long hold is
            # the dead-frame failure again, so it keeps a slow push of its own.
            js.append(f'      tl.to("#{bid}", {{scale:1.05, duration:{max(0.5, round(t1-at,3))}, '
                      f'ease:"none"}}, {at});')
            if bx.get("out"):
                js.append(f'      tl.to("#{bid}", {{autoAlpha:0, duration:0.18}}, {bx["out"]});')

        for j, ic in enumerate(s.get("icons", []), 1):
            iid = f"{sid}i{j}"
            colour = "#111111" if white else "#FFFFFF"
            body = ICON_SVG[ic["kind"]].replace("{c}", colour)
            html.append(f'        <svg class="ov" id="{iid}"><g transform="translate('
                        f'{round(ic["x"]*1920)},{round(ic["y"]*1080)}) scale({ic.get("scale",1)})">'
                        f'{body}</g></svg>')
            at = ic.get("at", t0)
            js.append(f'      tl.fromTo("#{iid}", {{autoAlpha:0, scale:0.0, transformOrigin:"50% 50%"}}, '
                      f'{{autoAlpha:1, scale:1, duration:0.2, ease:"back.out(2)"}}, {at});')
            if ic.get("react"):
                js.append(f'      tl.to("#{iid}", {{rotation:{ic["react"]}, x:"+={ic.get("dx",0)}", '
                          f'duration:0.42, ease:"power3.out"}}, {ic["react_at"]});')
        html.append('      </div>')

        # HELD SHOTS. Vu is under 5% change for 30.8% of his runtime while still
        # having 26.7% over 40%. That shape needs BOTH: hard cuts, and framings
        # that genuinely sit still between them. A first pass that animated every
        # shot hit the change target and collapsed stillness to 1.6%, which is
        # the idle-wobble failure. On a held shot the image does not move; a pop
        # still animates over it, so the frame is never dead.
        if s.get("hold"):
            if not white:
                js.append(f'      gsap.set("#{sid}p", {{scale:{s.get("plate_scale",[1.08])[0]}}});')
            if s.get("asset"):
                fx, fy, fs = s["from_"]
                js.append(f'      gsap.set("#{sid}c", {{xPercent:-50, yPercent:-50, '
                          f'x:{round(fx*1920)}, y:{round(fy*1080)}, scale:{fs}}});')
            continue

        # plate: a slow continuous travel that ARRIVES, never a drift to fill time
        if not white:
            ps, pe = s.get("plate_scale", [1.06, 1.13])
            js.append(f'      gsap.set("#{sid}p", {{scale:{ps}}});')
            js.append(f'      tl.to("#{sid}p", {{scale:{pe}, duration:{length}, ease:"none"}}, {t0});')
        if s.get("asset"):
            fx, fy, fs = s["from_"]
            tx, ty, ts = s["to"]
            js.append(f'      gsap.set("#{sid}c", {{xPercent:-50, yPercent:-50, '
                      f'x:{round(fx*1920)}, y:{round(fy*1080)}, scale:{fs}}});')
            js.append(f'      tl.to("#{sid}c", {{x:{round(tx*1920)}, y:{round(ty*1080)}, '
                      f'scale:{ts}, duration:{length}, ease:"none"}}, {t0});')

    # A pop's fade-out must not END on a clip boundary: a seek can land after
    # the tween and leave stale visibility. Pull every exit clear of the next cut.
    cuts = sorted({sh["t0"] for sh in shots} | {sh["t1"] for sh in shots})
    for p in sheet.get("pops", []):
        for c in cuts:
            if 0 <= c - p["t1"] < 0.25:
                p["t1"] = round(c - 0.3, 3)
                break

    # pops live on their own track so a cut never orphans one mid-word
    for n, p in enumerate(sheet.get("pops", []), 1):
        pid = f"pop{n:02d}"
        cls = "pop " + p.get("style", "")
        html.append(f'      <div id="{pid}" class="clip {cls}" data-start="{p["t0"]}" '
                    f'data-duration="{round(p["t1"]-p["t0"],3)}" data-track-index="{5+n}" '
                    f'style="top:{p.get("y",800)}px;">{p["text"]}</div>')
        js.append(f'      tl.fromTo("#{pid}", {{autoAlpha:0, y:24, scale:0.95}}, '
                  f'{{autoAlpha:1, y:0, scale:1, duration:0.2, ease:"back.out(1.7)"}}, {p["t0"]});')
        js.append(f'      tl.to("#{pid}", {{autoAlpha:0, duration:0.14}}, {round(p["t1"]-0.14,3)});')
        js.append(f'      tl.set("#{pid}", {{autoAlpha:0}}, {p["t1"]});')

    # persistent title, one clip per contiguous ground run so the fill can flip
    for n, t in enumerate(sheet["titles"], 1):
        tid = f"t{n:02d}"
        cls = "title onWhite" if t["white"] else "title"
        html.append(f'      <div id="{tid}" class="clip {cls}" data-start="{t["t0"]}" '
                    f'data-duration="{round(t["t1"]-t["t0"],3)}" data-track-index="{40+n}">'
                    f'{sheet["creature"]}</div>')
        js.append(f'      tl.from("#{tid}", {{y:-26, autoAlpha:0, duration:0.34, ease:"power3.out"}}, {t["t0"]});')

    open(out_html, "w").write("".join(x + "\n" for x in html) +
                              TAIL.replace("{body}", "\n".join(js)))
    ins = sum(len(s.get("inserts", [])) for s in shots)
    ico = sum(len(s.get("icons", [])) for s in shots)
    print(f"{len(shots)} shots, {ins} inserts, {ico} icons, "
          f"{len(sheet.get('pops',[]))} pops -> {out_html}")
    cuts = [s["t0"] for s in shots]
    gaps = [round(cuts[i+1]-cuts[i], 2) for i in range(len(cuts)-1)] or [0]
    dur = sheet["duration"]
    # Both numbers matter and they pull in opposite directions. Cuts per minute
    # is measured at 15.2 for the reference. Seconds-per-EVENT is the other
    # half: a long hold is only allowed because things keep happening inside it.
    events = len(cuts) + ins + ico + len(sheet.get("pops", []))
    print(f"  {60.0*len(cuts)/dur:.1f} cuts/min (reference 15.2), "
          f"longest hold {max(gaps):.1f}s (reference 23.1s)")
    print(f"  an event every {dur/max(1,events):.1f}s (house max unchanged frame 4.0s)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet"); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    build(json.load(open(a.sheet)), a.out)
