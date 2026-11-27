set -e
cd /home/user/Test-2
S=.claude/skills/explaintory-voiceover/scripts
W=out/blackholes/.vo_Every_Ultramassive_Black_Hole_Explained_in_13_Minutes
python3 $S/generate.py --script $W/narration_source.txt --out $W/raw_stitched.wav --parts-dir $W/parts --sections-json $W/sections.json --max-chunk 450 --spend-log $W/spend.json --profile voice-calibration.v4.json --lexicon out/blackholes/lexicon.json --stitch-only --no-level-headings --before-heading-pause 0.52:0.66 --after-heading-pause 0.35:0.50
cp $W/raw_stitched.wav $W/stitch_plain.wav
ffmpeg -y -v error -i $W/stitch_plain.wav -af "volume=-3dB,highpass=f=70:poles=2,treble=g=-5:f=9500:t=s:w=0.7,atempo=1.05" -c:a pcm_f32le $W/stitch_chain.wav
python3 -c "
import soundfile as sf,numpy as np,sys
x,_=sf.read('$W/stitch_chain.wav'); p=20*np.log10(np.abs(x).max()); print(f'chain peak {p:.2f} dBFS'); sys.exit(0 if p<-0.5 else 3)"
cp $W/stitch_chain.wav $W/raw_stitched.wav
python3 $S/voiceover.py --script out/blackholes/script.md --title "Every Ultramassive Black Hole Explained in 13 Minutes" --profile voice-calibration.v4.json --out-dir out/blackholes --work $W --curated out/blackholes/curated.txt --from master
