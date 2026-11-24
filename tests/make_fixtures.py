"""Generira probne klipove sa sintetskim hrvatskim govorom (espeak-ng) i poznatim vremenima riječi.
Pokretanje iz prazne mape: python tests/make_fixtures.py ; zatim premjesti klip1.mp4, klip2.mp4 i mockwords.json u tests/fixtures/."""
import subprocess, json, wave, os
P1=[("Bok, ja sam Marko iz Kutine.",0.8),("Danas vam pokazujem kako",0.6),("Danas vam pokazujem kako očistiti klimu.",0.7),("eee",0.5),("Prvi korak je isključiti struju.",0.9)]
P2=[("Drugi korak, skinite filter i operite ga mlakom vodom.",1.0),("To je to, vidimo se u Sunčanom putu!",0.6)]
def wavdur(p):
    w=wave.open(p); return w.getnframes()/w.getframerate()
def build(name,phr):
    parts=[];words=[];t=0.4
    sil=lambda d,f: subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i",f"anullsrc=r=22050:cl=mono","-t",str(d),f],check=True)
    sil(0.4,f"{name}_s0.wav"); parts.append(f"{name}_s0.wav")
    for i,(txt,gap) in enumerate(phr):
        f=f"{name}_p{i}.wav"
        subprocess.run(["espeak-ng","-v","hr","-s","150","-w",f,txt],check=True)
        d=wavdur(f); toks=txt.split(); tot=sum(len(x) for x in toks); acc=0
        a0=t+0.08; a1=t+d-0.12
        for x in toks:
            s=a0+(a1-a0)*acc/tot; acc+=len(x); e=a0+(a1-a0)*acc/tot
            words.append({"w":x,"s":round(s,3),"e":round(e-0.03,3),"p":0.95})
        parts.append(f); t+=d
        g=f"{name}_g{i}.wav"; sil(gap,g); parts.append(g); t+=gap
    open(f"{name}.txt","w").write("".join(f"file '{p}'\n" for p in parts))
    subprocess.run(["ffmpeg","-y","-v","error","-f","concat","-i",f"{name}.txt","-ar","48000",f"{name}.wav"],check=True)
    return words,t
w1,d1=build("c1",P1); w2,d2=build("c2",P2)
# klip 1: vodoravni 1920x1080, klip 2: okomiti
subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i",f"testsrc2=s=1920x1080:r=29.97:d={d1}","-i","c1.wav","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-shortest","klip1.mp4"],check=True)
subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i",f"gradients=s=1080x1920:r=30:d={d2}:speed=0.02,drawgrid=w=120:h=120:t=2:c=white@0.4","-i","c2.wav","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-shortest","klip2.mp4"],check=True)
json.dump({"w1":w1,"w2":w2},open("mockwords.json","w"),ensure_ascii=False)
print(d1,d2,len(w1),len(w2))
