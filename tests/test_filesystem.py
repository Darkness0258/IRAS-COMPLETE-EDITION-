from iras.tools.filesystem import write_text,read_text,list_directory,copy_path,move_path

def test_file_ops(tmp_path):
    a=tmp_path/'a.txt'; write_text(str(a),'hello'); assert read_text(str(a))=='hello'; assert list_directory(str(tmp_path))[0]['name']=='a.txt'; b=tmp_path/'b.txt'; copy_path(str(a),str(b)); assert b.read_text()=='hello'; c=tmp_path/'c.txt'; move_path(str(b),str(c)); assert c.exists()
