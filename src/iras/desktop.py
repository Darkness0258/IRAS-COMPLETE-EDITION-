from __future__ import annotations
import queue,threading,tkinter as tk
from tkinter import messagebox
from iras.bootstrap import build_runtime
from iras.models import ApprovalRequest
from iras.voice.tts import Speaker
from iras.voice.stt import Listener
from iras.config import Settings

class App:
    def __init__(self):
        self.root=tk.Tk(); self.root.title('IRAS'); self.root.geometry('980x680'); self.root.configure(bg='#090b10'); self.q=queue.Queue(); self.approval_q=queue.Queue(); self.settings=Settings.load(); self.speaker=Speaker(self.settings.tts_provider,self.settings.voice); self.listener=Listener(self.settings.whisper_model,self.settings.listen_seconds); self.voice_on=tk.BooleanVar(value=True)
        self.rt=build_runtime(self.settings,self.approve)
        self.chat=tk.Text(self.root,bg='#0f131c',fg='#e8ecf3',insertbackground='white',font=('Segoe UI',11),relief='flat',wrap='word'); self.chat.pack(fill='both',expand=True,padx=18,pady=(18,10)); self.chat.insert('end','IRAS > Online.\n\n'); self.chat.config(state='disabled')
        bar=tk.Frame(self.root,bg='#090b10'); bar.pack(fill='x',padx=18,pady=(0,18)); self.entry=tk.Entry(bar,bg='#151b27',fg='white',insertbackground='white',font=('Segoe UI',11),relief='flat'); self.entry.pack(side='left',fill='x',expand=True,ipady=10); self.entry.bind('<Return>',lambda e:self.send())
        tk.Button(bar,text='Send',command=self.send,padx=18,pady=8).pack(side='left',padx=(8,0)); tk.Button(bar,text='Speak',command=self.listen,padx=18,pady=8).pack(side='left',padx=(8,0)); tk.Checkbutton(bar,text='Voice replies',variable=self.voice_on,bg='#090b10',fg='white',selectcolor='#151b27',activebackground='#090b10').pack(side='left',padx=12)
        self.root.after(100,self.poll)
    def append(self,text): self.chat.config(state='normal'); self.chat.insert('end',text+'\n\n'); self.chat.see('end'); self.chat.config(state='disabled')
    def approve(self,req:ApprovalRequest):
        event=threading.Event(); box={}
        self.approval_q.put((req,event,box))
        event.wait()
        return bool(box.get('v'))
    def send(self):
        text=self.entry.get().strip()
        if not text:return
        self.entry.delete(0,'end'); self.append('You > '+text); threading.Thread(target=self.work,args=(text,),daemon=True).start()
    def work(self,text):
        try: ans=self.rt.agent.handle(text)
        except Exception as e: ans=f'Error: {type(e).__name__}: {e}'
        self.q.put(('answer',ans))
    def listen(self):
        self.append(f'IRAS > Listening for {self.settings.listen_seconds} seconds...'); threading.Thread(target=self.listen_work,daemon=True).start()
    def listen_work(self):
        try:
            text=self.listener.listen_once(); self.q.put(('heard',text))
        except Exception as e:self.q.put(('answer',f'Voice input unavailable: {e}'))
    def poll(self):
        try:
            while True:
                req,event,box=self.approval_q.get_nowait()
                box['v']=messagebox.askyesno('IRAS approval',f'{req.tool_name}\nPermission: {req.permission.name}\n\n{req.arguments}\n\nApprove?')
                event.set()
        except queue.Empty: pass
        try:
            while True:
                kind,val=self.q.get_nowait()
                if kind=='heard': self.append('You > '+val); threading.Thread(target=self.work,args=(val,),daemon=True).start()
                else:
                    self.append('IRAS > '+val)
                    if self.voice_on.get(): threading.Thread(target=lambda: self.speaker.speak(val),daemon=True).start()
        except queue.Empty: pass
        self.root.after(100,self.poll)
    def run(self): self.root.mainloop()
def main(): App().run()
