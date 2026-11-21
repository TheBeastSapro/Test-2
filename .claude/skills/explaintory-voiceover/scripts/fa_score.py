import sys,subprocess,torch,torchaudio,numpy as np
f,a,b=sys.argv[1],float(sys.argv[2]),float(sys.argv[3]); cands=sys.argv[4:]
raw=subprocess.check_output(["ffmpeg","-v","error","-ss",str(a),"-t",str(b-a),"-i",f,"-ac","1","-ar","16000","-f","f32le","-"])
w=torch.from_numpy(np.frombuffer(raw,np.float32).copy())[None]
B=torchaudio.pipelines.MMS_FA; m=B.get_model(); d=B.get_dict()
with torch.inference_mode(): em,_=m(w)
lp=torch.log_softmax(em,-1)
for c in cands:
    toks=[d[ch] for ch in c.lower().replace("'","") .replace(" ","*") if ch in d]
    ali,sc=torchaudio.functional.forced_align(lp,torch.tensor([toks]),blank=0)
    print(f"{c!r:40} mean logp {sc[0][ali[0]!=0].mean().item() if False else sc[0].mean().item():.4f}  total {sc[0].sum().item():.1f}")
