"""AI 工具调用镜像插件 —— 可粘贴文件类型清单

职责：定义哪些扩展名的文件适合以「文本附件」形式贴进网页 AI 输入框。

用途：read_file 开启附件粘贴投递时，先查本清单；扩展名不在清单内，
      正文改走结果直返（JSON 结构体），避免浏览器构造附件失败。

清单形态：逗号分隔的扩展名，统一转小写后按「带前导点的后缀」匹配。
以点开头且整名只有一个点的文件（如 .gitignore、.env）没有主名，
网页 AI 无法将其识别为附件，故一律不参与附件粘贴，正文改走结果直返。
"""
import os


# 可粘贴的扩展名清单。逗号分隔，每行若干项，便于阅读与维护。
# 覆盖源码、标记、配置、文档、表格、图片等常见可直接作为附件的类型。
PASTEABLE_EXT_TEXT = """
.wxml,.wxss,.wxs,.axml,.acss,.sjs,.swan,.ttml,
.ttss,.qml,.qss,.pdf,.png,.jpg,.jpeg,.svg,
.svgz,.bmp,.gif,.webp,.ico,.xbm,.dib,.pjp,
.tif,.pjpeg,.avif,.apng,.tiff,.jfif,.txt,.md,
.csv,.tsv,.html,.json,.log,.dot,.go,.h,
.c,.cpp,.cxx,.cc,.cs,.java,.js,.css,
.jsp,.php,.py,.py3,.asp,.yaml,.yml,.ini,
.conf,.ts,.tsx,.doc,.docx,.ppt,.pptx,.xls,.xlsx,
.abap,.asc,.ash,.ampl,.mod,.g4,.apib,.apl,
.dyalog,.asax,.ascx,.ashx,.asmx,.aspx,.axd,.dats,
.hats,.sats,.as,.adb,.ada,.ads,.agda,.als,
.apacheconf,.vhost,.cls,.applescript,.scpt,.arc,.ino,
.asciidoc,.adoc,.aj,.asm,.a51,.inc,.nasm,.aug,
.ahk,.ahkl,.au3,.awk,.auk,.gawk,.mawk,.nawk,
.bat,.cmd,.befunge,.bison,.bb,.decls,.bmx,.bsv,
.boo,.b,.bf,.brs,.bro,.cats,.idc,.w,
.cake,.cshtml,.csx,.c++,.cp,.h++,.hh,.hpp,
.hxx,.inl,.ipp,.tcc,.tpp,.c-objdump,.chs,.clp,
.cmake,.in,.cob,.cbl,.ccp,.cobol,.cpy,.capnp,
.mss,.ceylon,.chpl,.ch,.ck,.cirru,.clw,.icl,
.dcl,.click,.clj,.boot,.cl2,.cljc,.cljs,.hl,
.cljscm,.cljx,.hic,.coffee,._coffee,.cjsx,.cjs,.cts,
.mjs,.mts,.cson,.iced,.cfm,.cfml,.cfc,.lisp,
.asd,.cl,.l,.lsp,.ny,.podsl,.sexp,.cps,
.coq,.v,.cppobjdump,.c++-objdump,.c++objdump,
.cpp-objdump,.cxx-objdump,.creole,.cr,.feature,.cu,.cuh,
.cy,.pyx,.pxd,.pxi,.d,.di,.d-objdump,.com,
.dm,.zone,.arpa,.darcspatch,.dpatch,.dart,.diff,.patch,
.dockerfile,.djs,.dylan,.dyl,.intr,.lid,.e,.ecl,
.eclxml,.sch,.brd,.epj,.ex,.exs,.elm,.el,
.emacs,.desktop,.em,.emberscript,.erl,.es,.escript,.hrl,
.xrl,.yrl,.fs,.fsi,.fsx,.fx,.flux,.f90,
.f,.f03,.f08,.f77,.f95,.for,.fpp,.factor,
.fy,.fancypack,.fan,.fth,.4th,.forth,.fr,.frt,
.ftl,.g,.gco,.gcode,.gms,.gap,.gd,.gi,
.tst,.s,.ms,.glsl,.fp,.frag,.frg,.fsh,
.fshader,.geo,.geom,.glslv,.gshader,.shader,.vert,.vrx,
.vsh,.vshader,.gml,.kid,.ebuild,.eclass,.po,.pot,
.glf,.gp,.gnu,.gnuplot,.plot,.plt,.golo,.gs,
.gst,.gsx,.vark,.grace,.gradle,.gf,.graphql,.gv,
.man,.1in,.1m,.1x,.3in,.3m,.3qt,.3x,
.me,.n,.rno,.roff,.groovy,.grt,.gtpl,.gvy,
.gsp,.hcl,.tf,.hlsl,.fxh,.hlsli,.htm,.st,
.xht,.xhtml,.mustache,.jinja,.eex,.erb,.deface,.phtml,
.http,.haml,.handlebars,.hbs,.hb,.hs,.hsc,.hx,
.hxsl,.hy,.pro,.dlm,.ipf,.cfg,.prefs,.properties,
.irclog,.weechatlog,.idr,.lidr,.ni,.i7x,.iss,.io,
.ik,.thy,.ijs,.flex,.jflex,.geojson,.lock,.topojson,
.json5,.jsonld,.jq,.jsx,.jade,.j,._js,.bones,
.es6,.jake,.jsb,.jscad,.jsfl,.jsm,.jss,.njs,
.pac,.ssjs,.sublime-build,.sublime-commands,
.sublime-completions,.sublime-keymap,.sublime-macro,
.sublime-menu,.sublime-mousemap,.sublime-project,
.sublime-settings,.sublime-theme,.sublime-workspace,
.sublime_metrics,.sublime_session,.xsjs,.xsjslib,.jl,.ipynb,
.krl,.kicad_pcb,.kit,.kt,.ktm,.kts,.lfe,
.ll,.lol,.lsl,.lslp,.lvproj,.lasso,.las,
.lasso8,.lasso9,.ldml,.latte,.lean,.hlean,.less,
.lex,.ly,.ily,.m,.ld,.lds,.liquid,
.lagda,.litcoffee,.lhs,.ls,._ls,.xm,.x,
.xi,.lgt,.logtalk,.lookml,.lua,.fcgi,.nse,
.pd_lua,.rbxs,.wlua,.mumps,.m4,.mcfunction,.mcr,
.mtml,.muf,.mak,.mk,.mkfile,.mako,.mao,
.markdown,.mkd,.mkdn,.mkdown,.ron,.mask,.mathematica,
.cdf,.ma,.map,.mt,.nb,.nbp,.wl,
.wlt,.matlab,.maxpat,.maxhelp,.maxproj,.mxt,.pat,
.mediawiki,.wiki,.moo,.metal,.minid,.druby,.duby,
.mir,.mirah,.mo,.mms,.mmk,.monkey,.moon,
.myt,.ncl,.nl,.nsi,.nsh,.axs,.axi,
.nlogo,.nginxconf,.nim,.nimrod,.ninja,.nit,.nix,
.nu,.numpy,.numpyw,.numsc,.ml,.eliom,.eliomi,
.ml4,.mli,.mll,.mly,.objdump,.mm,.sj,
.omgrofl,.opa,.opal,.opencl,.p,.scad,.org,
.ox,.oxh,.oxo,.oxygene,.oz,.pwn,.aw,
.ctp,.php3,.php4,.php5,.php6,.php7,.php8,
.phps,.phpt,.pls,.pck,.pkb,.pks,.plb,
.plsql,.sql,.pov,.pan,.psc,.parrot,.pasm,
.pir,.pas,.dfm,.dpr,.lpr,.pp,.pl,
.al,.cgi,.perl,.ph,.plx,.pm,.pod,
.psgi,.t,.6pl,.6pm,.nqp,.p6,.p6l,
.p6m,.pl6,.pm6,.pkl,.pig,.pike,.pmod,
.pogo,.pony,.ps,.eps,.ps1,.psd1,.psm1,
.pde,.prolog,.yap,.spin,.proto,.pub,.pd,
.pb,.pbi,.purs,.bzl,.gyp,.lmi,.pyde,
.pyi,.pyp,.pyt,.pyw,.rpy,.tac,.wsgi,
.xpy,.pytb,.qml,.qbs,.pri,.r,.rd,
.rsx,.raml,.rdoc,.rbbas,.rbfrm,.rbmnu,.rbres,
.rbtbar,.rbuistate,.rhtml,.rmd,.rkt,.rktd,.rktl,
.scrbl,.rl,.raw,.reb,.r2,.r3,.rebol,
.red,.reds,.cw,.rs,.rsh,.robot,.rg,
.rb,.builder,.gemspec,.god,.irbrc,.jbuilder,.mspec,
.pluginspec,.podspec,.rabl,.rake,.rbuild,.rbw,.rbx,
.ru,.ruby,.thor,.watchr,.sas,.scss,.smt2,
.smt,.sparql,.rq,.sqf,.hqf,.cql,.ddl,
.prc,.tab,.udf,.viw,.db2,.ston,.sage,
.sagews,.sls,.sass,.scala,.sbt,.sc,.scaml,
.scm,.sld,.sps,.ss,.sci,.sce,.self,
.sh,.bash,.bats,.command,.ksh,.tmux,.tool,
.zsh,.sh-session,.shen,.sl,.slim,.smali,.tpl,
.sp,.sma,.nut,.stan,.fun,.sig,.sml,
.do,.ado,.doh,.ihlp,.mata,.matah,.sthlp,
.styl,.scd,.swift,.sv,.svh,.vh,.toml,
.txl,.tcl,.adp,.tm,.tcsh,.csh,.tex,
.aux,.bbx,.bib,.cbx,.dtx,.ins,.lbx,
.ltx,.mkii,.mkiv,.mkvi,.sty,.toc,.tea,
.no,.textile,.thrift,.tu,.ttl,.twig,.upc,
.anim,.asset,.meta,.prefab,.unity,.uno,.uc,
.ur,.urs,.vcl,.vhdl,.vhd,.vhf,.vhi,
.vho,.vhs,.vht,.vhw,.vala,.vapi,.veo,
.vim,.vb,.bas,.frm,.frx,.vba,.vbhtml,
.vbs,.volt,.vue,.owl,.webidl,.x10,.xc,
.xml,.ant,.ccxml,.clixml,.cproject,.csl,.csproj,
.ct,.dita,.ditamap,.ditaval,.config,.dotsettings,.filters,
.fsproj,.fxml,.glade,.grxml,.iml,.ivy,.jelly,
.jsproj,.kml,.launch,.mdpolicy,.mxml,.nproj,.nuspec,
.odd,.osm,.plist,.props,.ps1xml,.psc1,.pt,
.rdf,.rss,.scxml,.srdf,.storyboard,.sttheme,
.sublime-snippet,.targets,.tmcommand,.tml,.tmlanguage,
.tmpreferences,.tmsnippet,.tmtheme,.ui,.urdf,.ux,.vbproj,
.vcxproj,.vssettings,.vxml,.wsdl,.wsf,.wxi,.wxl,
.x3d,.xacro,.xaml,.xib,.xlf,.xliff,.xmi,
.dist,.xproj,.xsd,.xul,.zcml,.xsp-config,.metadata,
.xpl,.xproc,.xquery,.xq,.xql,.xqm,.xqy,
.xs,.xslt,.xsl,.xojo_code,.xojo_menu,.xojo_report,
.xojo_script,.xojo_toolbar,.xojo_window,.xtend,.reek,.rviz,
.sublime-syntax,.syntax,.yang,.y,.yacc,.yy,
.zep,.zimpl,.zmpl,.zpl,.ec,.eh,.edn,
.fish,.mu,.nc,.ooc,.rst,.rest,.wisp,
.prg,.prw,.gitignore,.gitkeep,.gitmodules,.example,
.avifs,.blp,.bufr,.bw,.cur,.dcx,.dds,
.emf,.fit,.fits,.flc,.fli,.ftc,.ftu,
.gbr,.grib,.h5,.hdf,.hif,.icb,.icns,
.iim,.im,.j2c,.j2k,.jp2,.jpc,.jpe,
.jpf,.jpx,.mpeg,.mpg,.msp,.pbm,.pcd,
.pcx,.pfm,.pgm,.pnm,.ppm,.pxr,.qoi,
.ras,.rgb,.rgba,.sgi,.tga,.vda,.vst,
.wmf,.xpm,.epub,.mobi,
.zip,.rar,.7z,.tar,.gz,.tgz,.bz2,.xz,
.zst,.cab,.iso,.jar,.war,.apk,.whl
"""


def _parse(text):
    """把逗号分隔的清单解析为小写后缀集合。

    @param text 原始清单文本
    @returns 小写后缀集合（每项带前导点）
    """
    out = set()
    for item in str(text or "").split(","):
        s = item.strip().lower()
        if s:
            out.add(s)
    return out


# 解析结果：模块加载时算一次，后续判定只做集合查询
PASTEABLE_EXTS = _parse(PASTEABLE_EXT_TEXT)


def suffix_of(file_path):
    """取文件的可匹配后缀：普通文件取末段扩展名，点开头无扩展名取整名。

    例：a/b/readme.md → .md；a/b/.gitignore → .gitignore；a/b/Makefile → 空串。
    @param file_path 文件路径
    @returns 小写后缀（带前导点）；无法判定时返回空串
    """
    import os
    name = os.path.basename(str(file_path or "")).lower()
    if not name:
        return ""
    # 点开头且仅一个点（.gitignore 这类）：整名即后缀，避免被当成无扩展名
    if name.startswith(".") and name.count(".") == 1:
        return name
    idx = name.rfind(".")
    if idx < 0:
        return ""
    return name[idx:]


def is_pasteable(file_path):
    """判断某文件是否属于可作为附件粘贴的类型。

    以点开头且整名只有一个点的文件（.gitignore、.env 这类）没有主名，
    网页 AI 无法把它们识别为附件，故无论是否在清单内都判定为不可粘贴。
    @param file_path 文件路径
    @returns 可作为附件粘贴返回 True
    """
    # 无主名的点文件：整个文件名以点开头且只含一个点（如 .gitignore、.env），
    # 没有主名可供网页识别，无论后缀是否在清单内都不走附件粘贴。
    name = os.path.basename(str(file_path or "")).lower()
    if name.startswith(".") and name.count(".") == 1:
        return False
    return suffix_of(file_path) in PASTEABLE_EXTS
