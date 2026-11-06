"""Compose a one-page Chinese progress brief from the pinned, real rerun."""
from pathlib import Path
import hashlib
import json
import sys
import importlib.metadata
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as PDFImage
from reportlab.lib.pagesizes import A4
from pypdf import PdfReader

case=Path(__file__).resolve().parents[1]
out=case/'presentation';out.mkdir(exist_ok=True)
run=case/'outputs/20261102T144055_167379Z'
checks=json.loads((run/'checks.json').read_text())
assert all(checks['passed'].values())
font_path='C:/Windows/Fonts/simhei.ttf'
canvas=Image.new('RGB',(2000,650),'white');draw=ImageDraw.Draw(canvas)
font=ImageFont.truetype(font_path,36)
draw.text((25,18),'[原文] Lieu 2018，图4（arXiv v2，第4页）',font=font,fill='#19334b')
draw.text((1030,18),'[推导] 本轮按图注计算（801个参数点）',font=font,fill='#19334b')
for path,x in [(case/'source/figure4_crop.png',30),(run/'spectrum_refined.png',1030)]:
    im=Image.open(path).convert('RGB');im.thumbnail((940,480))
    # Enlarge the original for a readable side-by-side comparison; preserve aspect ratio.
    ratio=min(940/im.width,480/im.height)
    im=im.resize((round(im.width*ratio),round(im.height*ratio)),Image.Resampling.LANCZOS)
    canvas.paste(im,(x+(940-im.width)//2,75+(480-im.height)//2))
small=ImageFont.truetype(font_path,27)
draw.text((30,570),'两图均为能量实部、虚部；未重标能量。原图红色为作者边界态，本轮红色为端点权重判据。',font=small,fill='#344054')
draw.text((30,610),'[未知] 图像端点与图注不符，原因待核实。此图展示差异，不代表完整定量复现。',font=small,fill='#a54225')
canvas.save(out/'comparison.png')

sections=[
('导师任务与目前定位','尝试构建可用于不同论文的文献结果复现 agent。当前是 Codex 驱动的轻量流程原型，以 Lieu 的非厄米 SSH 模型图4为首例；这是“有详细指导的复现”，跨论文迁移尚未验证。'),
('本周实际完成（2026-11-02）','在10月30日已有计算的基础上，审查原文、源码及两轮日志；补配置限制与文件哈希检查；保留旧结果，按相同配置重跑；整理贡献记录、迁移任务单与三分钟演示。完整计算实测246.33秒，归档回读检查4.31秒。'),
('模型与目标依据','[原文] PDF页序1式(1)(2)、页序4（印刷页4）图注：u=0，v1=v2=exp(iπ/5)sin(t)，w1=w2=cos(t)，100个原胞。[推导] 构建200阶开放链矩阵，求一般复数本征值；不加末端连接。'),
('最关键的验证与差异','[推导] 七类预设数值检查通过；最大归一化残差2.19e-15，二聚体极限误差1.15e-15以内。低t近零边界分支、±E配对定性一致，但在t=π/2，图注模型正分支为(Re E, Im E)=(0.8090, 0.5878)，旧图像读数约(0.302, 0.938)。[假设] 读图保守误差各±0.03，不是作者原始数据。'),
('agent 的作用与人工介入','我提供任务、范围、参数线索和详细验证建议；Codex 核对材料、写程序、调用求解器、归档并检查结果。数值由NumPy/SciPy计算。GPD只复用验证报告格式及格式校验，未运行完整工作流；没有证据表明我手写了求解代码或逐项审核了公式。'),
('当前不足与下一步','[未知] 用户确认暂无作者代码、原始数据或勘误；原图差异原因未明，不能称为图4完整定量复现。[假设] 端点阈值是数值选择，会漏标弱局域态。下一步：用另一篇论文的明确目标做一次冻结流程、只给材料和资源限制的迁移测试，逐次记录人工帮助。')]
pdfmetrics.registerFont(TTFont('CN',font_path))
body=ParagraphStyle('body',fontName='CN',fontSize=10.3,leading=15.1,textColor=colors.HexColor('#243347'),spaceAfter=6)
head=ParagraphStyle('head',parent=body,fontSize=11.5,leading=16,textColor=colors.HexColor('#145b78'),spaceBefore=3,spaceAfter=3)
title=ParagraphStyle('title',parent=body,fontSize=20,leading=26,spaceAfter=5)
sub=ParagraphStyle('sub',parent=body,fontSize=9,leading=12,textColor=colors.HexColor('#667085'))
story=[Paragraph('文献结果复现 agent｜阶段汇报',title),Paragraph('物理专业大二 · 2026-11-02 · 可重跑的指导案例，尚未证明通用性',sub)]
for i,(h,t) in enumerate(sections):
    story.extend([Paragraph(h,head),Paragraph(t,body)])
    if i==2:
        story.extend([PDFImage(str(out/'comparison.png'),width=515,height=167.375),Spacer(1,5)])
story.append(Paragraph('证据：cases/lieu2018-fig4/outputs/20261102T144055_167379Z；checks.json、archive_audit.json。依据与贡献详见 extraction.md、records/audit-20261102.md。',sub))
pdf=out/'briefing.pdf'
SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=39,leftMargin=39,topMargin=30,bottomMargin=28,title='文献结果复现 agent 阶段汇报',author='项目阶段记录').build(story)
pages=len(PdfReader(pdf).pages)
assert pages==1, f'Expected one page, got {pages}'
md=['# 文献结果复现 agent：阶段汇报','', '2026-11-02；此前案例计算完成于10月30日，本周工作不重复计作首次实现。','']
for i,(h,t) in enumerate(sections):
    md += ['## '+h,'',t,'']
    if i==2: md += ['![原文与本轮结果对照](comparison.png)','']
(out/'briefing.md').write_text('\n'.join(md),encoding='utf-8')
meta={'command':[sys.executable,*sys.argv],'cwd':str(Path.cwd()),'pinned_run':str(run),'pages':pages,'python':sys.version,'packages':{k:importlib.metadata.version(k) for k in ['reportlab','pillow','pypdf']},'exit_code':0,'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'input_sha256':{str(p.relative_to(case)):hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in [case/'source/figure4_crop.png',run/'spectrum_refined.png',run/'checks.json']}}
(out/'build.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
print(json.dumps(meta,indent=2))
