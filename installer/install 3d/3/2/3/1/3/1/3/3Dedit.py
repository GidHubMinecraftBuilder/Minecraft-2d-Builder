from direct.showbase.ShowBase import ShowBase
from panda3d.core import DirectionalLight, AmbientLight, Vec4, TextNode, GeomVertexReader
from panda3d.core import Texture, PNMImage, WindowProperties, CollisionTraverser, CollisionNode, CollisionHandlerQueue, CollisionRay, BitMask32
from panda3d.core import GeomVertexData, GeomVertexFormat, GeomVertexWriter, GeomTriangles, Geom, GeomNode
from direct.gui.DirectGui import DirectButton, DirectFrame, OnscreenText
import sys
import os
# Импортируем проводник для выбора файлов
import tkinter as tk
from tkinter import filedialog

MOVE_SPEED = 0.5
SCALE_SPEED = 0.2
CAM_SPEED = 0.5
MOUSE_SENSITIVITY = 40.0

class Infinite3DStudio(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        self.setBackgroundColor(0.1, 0.1, 0.1)
        self.disableMouse() 

        # Настройка окна 1000x700
        properties = WindowProperties()
        properties.setSize(1000, 700)
        properties.setTitle("3D Sandbox: Infinite Blocks & OBJ Loader")
        self.win.requestProperties(properties)

        # Прячем главное окно tkinter, оно нужно только для диалога файлов
        self.tk_root = tk.Tk()
        self.tk_root.withdraw()

        self.is_editing = False
        self.active_object = None
        self.object_type = "None"
        self.all_objects = []  

        self.undo_stack = []
        self.redo_stack = []

        # Система кликов для выбора объектов
        self.picker = CollisionTraverser()
        self.pickerQueue = CollisionHandlerQueue()
        self.pickerNode = CollisionNode('mouseRay')
        self.pickerNP = self.camera.attachNewNode(self.pickerNode)
        self.pickerNode.setFromCollideMask(BitMask32.bit(1))
        self.pickerRay = CollisionRay()
        self.pickerNode.addSolid(self.pickerRay)
        self.picker.addCollider(self.pickerNP, self.pickerQueue)
        
        self.mouse_look_active = False
        self.last_mouse_pos = (0, 0)

        self.r_255, self.g_255, self.b_255 = 255, 255, 255

        self.textures = {
            "metal": self.create_procedural_texture(180, 180, 185, noise=True),
            "wood": self.create_procedural_texture(139, 69, 19, noise=False),
            "grass": self.create_procedural_texture(34, 139, 34, noise=True),
            "stone": self.create_procedural_texture(105, 105, 105, noise=True)
        }

        self.setup_menu()
        self.setup_lights()

    def create_procedural_texture(self, r, g, b, noise=False):
        img = PNMImage(256, 256)
        for x in range(256):
            for y in range(256):
                factor = 1.0
                if noise and (x + y) % 7 == 0: factor = 0.8  
                img.setXel(x, y, (r*factor)/255.0, (g*factor)/255.0, (b*factor)/255.0)
        tex = Texture()
        tex.load(img)
        return tex

    def setup_menu(self):
        self.menu_frame = DirectFrame(frameColor=(0, 0, 0, 0.6), frameSize=(-0.6, 0.6, -0.5, 0.5), pos=(0, 0, 0))
        OnscreenText(text="INFINITE 3D SANDBOX", parent=self.menu_frame, pos=(0, 0.3), scale=0.08, fg=(1, 1, 1, 1))
        DirectButton(text="START SANDBOX", parent=self.menu_frame, scale=0.08, pos=(0, 0, -0.05), command=self.start_editor)
        DirectButton(text="QUIT", parent=self.menu_frame, scale=0.08, pos=(0, 0, -0.25), command=sys.exit)

    def setup_lights(self):
        ambient = AmbientLight("ambient")
        ambient.setColor((0.5, 0.5, 0.5, 1))
        self.render.setLight(self.render.attachNewNode(ambient))

        directional = DirectionalLight("directional")
        directional.setColor((0.7, 0.7, 0.7, 1))
        dl_node = self.render.attachNewNode(directional)
        dl_node.setHpr(45, -45, 0)
        self.render.setLight(dl_node)

    def start_editor(self):
        self.menu_frame.hide()
        self.is_editing = True
        self.camera.setPos(0, -30, 15)  
        self.camera.lookAt(0, 0, 0)

        self.setup_ui_text()
        self.setup_controls()
        self.spawn_object("box", save_history=False) 

        self.taskMgr.add(self.mouse_look_task, "MouseLookTask")

    def setup_ui_text(self):
        self.ui_display = OnscreenText(text="", pos=(-1.35, 0.94), scale=0.031, fg=(1, 1, 1, 1), align=TextNode.ALeft, mayChange=True)
        self.toolbox_display = OnscreenText(text="", pos=(0.72, 0.94), scale=0.033, fg=(1, 0.9, 0.4, 1), align=TextNode.ALeft, mayChange=True)
        self.update_ui_info()

    def update_ui_info(self, extra_msg=""):
        controls_text = (
            "[ FILE & LOAD ]\n"
            "F1 : Save Active to Desktop  |  F2 : LOAD OBJ (Open Explorer) {extra_msg}\n\n"
            "[ HISTORY CONTROLS ]\n"
            "Ctrl + Z : Undo (Отменить)  |  Ctrl + Y : Redo (Повторить)\n\n"
            "[ MOUSE ]\n"
            "LMB (Левый Клик) : Select Object (Выбрать блок)\n"
            "Hold RMB (Правая Кнопка) + Move : Rotate Camera\n\n"
            "[ SPAWN TOOLBOX ]\n"
            "F5: BOX | F6: BALL | F7: TRIPLE BOX | Shift+1..2: Blocks 4 / 8\n"
            "Shift+3: Grass 100x100 | Shift+4: Stone | Shift+5: Platform 10x10\n\n"
            "[ PRESETS & MANIPULATION ]\n"
            "Ctrl+1..8: Colors/Presets | Arrows: Move X/Y | PgUp/PgDn: Move Z\n"
            "Textures: H, J, K, L | R/T, F/G, V/B: Edit RGB\n"
            "+ / - : Scale All  |  [ / ] : Scale X  |  ; / ' : Scale Y  |  . / / : Scale Z\n\n"
            "[ CAMERA ]  A/D/W/S/Q/E : Move Camera | ESC : Exit"
        )
        self.ui_display.setText(controls_text)

        active_id = self.all_objects.index(self.active_object) if self.active_object in self.all_objects else "None"
        toolbox_text = (
            "[ SANDBOX STATUS ]\n"
            "--------------------\n"
            f"Total Objects: {len(self.all_objects)}\n"
            f"Selected ID: {active_id}\n"
            f"Active Tool: {self.object_type.upper()}\n"
            "--------------------\n"
            f"Undo actions: {len(self.undo_stack)}\n"
            f"Redo actions: {len(self.redo_stack)}"
        )
        self.toolbox_display.setText(toolbox_text)

    def open_obj_explorer(self):
        """Открывает проводник файлов Explorer для выбора .obj файла"""
        file_path = filedialog.askopenfilename(
            title="Menu: Load OBJ",
            filetypes=[("Wavefront OBJ", "*.obj"), ("All Files", "*.*")]
        )
        if file_path:
            self.load_custom_obj(file_path)

    def load_custom_obj(self, file_path):
        """Парсит .obj файл и строит 3D геометрию прямо в движке"""
        vertices = []
        faces = []

        try:
            with open(file_path, 'r') as f:
                for line in f:
                    if line.startswith('#') or not line.strip():
                        continue
                    parts = line.split()
                    if not parts:
                        continue
                    
                    if parts[0] == 'v': # Вершина
                        # Читаем координаты X, Y, Z. Конвертируем оси под систему координат Panda3D
                        vertices.append((float(parts[1]), -float(parts[3]), float(parts[2])))
                    elif parts[0] == 'f': # Полигон (фейс)
                        face_indices = []
                        for part in parts[1:]:
                            # Убираем индексы текстур/нормалей (v/vt/vn), берем только первый индекс вершины
                            idx = int(part.split('/')[0])
                            # В OBJ индексация с 1, переводим в индексацию с 0
                            face_indices.append(idx - 1)
                        
                        # Если это четырехугольник (quad), триангулируем его вручную
                        if len(face_indices) == 3:
                            faces.append(face_indices)
                        elif len(face_indices) == 4:
                            faces.append([face_indices[0], face_indices[1], face_indices[2]])
                            faces.append([face_indices[0], face_indices[2], face_indices[3]])

            if not vertices:
                self.update_ui_info(extra_msg="(EMPTY OBJ!)")
                return

            # Создаем внутреннюю геометрию Panda3D на основе прочитанных данных
            vdata = GeomVertexData('obj_mesh', GeomVertexFormat.getV3n3t2(), Geom.UHStatic)
            vdata.setNumRows(len(vertices))
            
            vertex_writer = GeomVertexWriter(vdata, 'vertex')
            normal_writer = GeomVertexWriter(vdata, 'normal') # Базовые нормали, чтобы работало освещение
            
            for v in vertices:
                vertex_writer.addData3f(v[0], v[1], v[2])
                normal_writer.addData3f(0, 0, 1) 

            prim = GeomTriangles(Geom.UHStatic)
            for f in faces:
                prim.addVertices(f[0], f[1], f[2])

            geom = Geom(vdata)
            geom.addPrimitive(prim)
            
            node = GeomNode('imported_obj_node')
            node.addGeom(geom)
            
            # Создаем NodePath в нашей сцене
            new_node = self.render.attachNewNode(node)
            new_node.setPos(self.camera.getPos() + self.camera.getDirection() * 10) # Спавним перед камерой
            new_node.setScale(1.0, 1.0, 1.0)
            new_node.setCollideMask(BitMask32.bit(1)) # Включаем коллизию для возможности выделения кликом
            
            # Выделяем загруженный объект
            if self.active_object: self.active_object.clearColorScale()
            self.active_object = new_node
            self.active_object.setColorScale(1.4, 1.4, 1.4, 1)
            self.all_objects.append(new_node)
            
            filename = os.path.basename(file_path)
            self.object_type = f"OBJ: {filename[:12]}"
            self.save_state("spawn", new_node)
            self.update_ui_info(extra_msg="(LOADED!)")

        except Exception as e:
            print("Ошибка загрузки:", e)
            self.update_ui_info(extra_msg="(LOAD ERROR!)")

    def save_state(self, action_type, obj, old_pos=None, old_scale=None):
        state = {
            "type": action_type,
            "object": obj,
            "pos": old_pos if old_pos else obj.getPos() if obj else None,
            "scale": old_scale if old_scale else obj.getScale() if obj else None
        }
        self.undo_stack.append(state)
        self.redo_stack.clear()
        self.update_ui_info()

    def undo(self):
        if not self.undo_stack: return
        action = self.undo_stack.pop()
        obj = action["object"]

        if action["type"] == "spawn":
            if obj in self.all_objects:
                self.all_objects.remove(obj)
                if self.active_object == obj:
                    self.active_object = self.all_objects[-1] if self.all_objects else None
                obj.removeNode()
            action["type"] = "respawn"
            self.redo_stack.append(action)
        elif action["type"] in ["move", "scale"]:
            redo_action = {"type": action["type"], "object": obj, "pos": obj.getPos(), "scale": obj.getScale()}
            self.redo_stack.append(redo_action)
            obj.setPos(action["pos"])
            obj.setScale(action["scale"])
        self.update_ui_info()

    def redo(self):
        if not self.redo_stack: return
        action = self.redo_stack.pop()
        obj = action["object"]

        if action["type"] == "respawn":
            obj.reparentTo(self.render)
            self.all_objects.append(obj)
            self.active_object = obj
            action["type"] = "spawn"
            self.undo_stack.append(action)
        elif action["type"] in ["move", "scale"]:
            undo_action = {"type": action["type"], "object": obj, "pos": obj.getPos(), "scale": obj.getScale()}
            self.undo_stack.append(undo_action)
            obj.setPos(action["pos"])
            obj.setScale(action["scale"])
        self.update_ui_info()

    def select_object_under_mouse(self):
        if self.mouseWatcherNode.hasMouse():
            mpos = self.mouseWatcherNode.getMouse()
            self.pickerRay.setFromLens(self.camNode, mpos.getX(), mpos.getY())
            self.picker.traverse(self.render)
            
            if self.pickerQueue.getNumEntries() > 0:
                self.pickerQueue.sortEntries()
                entry = self.pickerQueue.getEntry(0)
                hit_node = entry.getIntoNodePath()
                
                for obj in self.all_objects:
                    if hit_node.isAncestorOf(obj) or hit_node == obj:
                        if self.active_object: self.active_object.clearColorScale()
                        self.active_object = obj
                        self.active_object.setColorScale(1.4, 1.4, 1.4, 1)
                        self.update_ui_info()
                        break

    def spawn_object(self, obj_type, save_history=True):
        self.object_type = obj_type
        new_node = None

        if obj_type == "box":
            new_node = self.loader.loadModel("models/box")
            new_node.setPos(-0.5, -0.5, -0.5) 
            flatten = self.render.attachNewNode("box_pivot")
            new_node.reparentTo(flatten)
            new_node = flatten
        elif obj_type == "ball":
            new_node = self.loader.loadModel("models/smiley")
        elif obj_type == "triple box":
            new_node = self.render.attachNewNode("triple_box_root")
            for offset in [-1.5, 0.0, 1.5]:
                cube = self.loader.loadModel("models/box")
                cube.setPos(offset - 0.5, -0.5, -0.5)
                cube.reparentTo(new_node)
        elif obj_type == "block 4": return self.spawn_custom_box((4, 4, 4), "block 4")
        elif obj_type == "block 8": return self.spawn_custom_box((8, 8, 8), "block 8")
        elif obj_type == "grass platform": return self.spawn_custom_box((100, 0.1, 100), "grass platform", "grass")
        elif obj_type == "stone block": return self.spawn_custom_box((2, 2, 2), "stone block", "stone")
        elif obj_type == "platform 10x10": return self.spawn_custom_box((10, 0.5, 10), "platform 10x10", "stone")

        if new_node:
            new_node.reparentTo(self.render)
            new_node.setPos(0, 0, 0)
            new_node.setScale(1.5, 1.5, 1.5)
            new_node.setCollideMask(BitMask32.bit(1))
            
            if self.active_object: self.active_object.clearColorScale()
            self.active_object = new_node
            self.all_objects.append(new_node)
            self.apply_color()
            
            if save_history: self.save_state("spawn", new_node)
            self.update_ui_info()

    def spawn_custom_box(self, scale, name, texture=None):
        self.spawn_object("box", save_history=False)
        self.object_type = name
        if self.active_object:
            self.active_object.setScale(*scale)
            if texture: self.apply_texture(texture)
            self.save_state("spawn", self.active_object)
        self.update_ui_info()

    def apply_texture(self, tex_name):
        if self.active_object and tex_name in self.textures:
            self.active_object.setTexture(self.textures[tex_name], 1)

    def apply_color(self):
        if self.active_object:
            self.active_object.setColor(Vec4(self.r_255/255.0, self.g_255/255.0, self.b_255/255.0, 1))

    def make_preset_box(self, r, g, b, texture_name=None):
        if self.active_object:
            self.r_255, self.g_255, self.b_255 = r, g, b
            self.apply_color()
            if texture_name: self.apply_texture(texture_name)
            else: self.active_object.clearTexture()
            self.update_ui_info()

    def set_mouse_look(self, active):
        self.mouse_look_active = active
        if active and self.mouseWatcherNode.hasMouse():
            self.last_mouse_pos = (self.mouseWatcherNode.getMouseX(), self.mouseWatcherNode.getMouseY())

    def mouse_look_task(self, task):
        if self.mouse_look_active and self.mouseWatcherNode.hasMouse():
            mx = self.mouseWatcherNode.getMouseX()
            my = self.mouseWatcherNode.getMouseY()
            dx = mx - self.last_mouse_pos[0]
            dy = my - self.last_mouse_pos[1]
            self.camera.setH(self.camera.getH() - dx * MOUSE_SENSITIVITY)
            self.camera.setP(self.camera.getP() + dy * MOUSE_SENSITIVITY)
            self.last_mouse_pos = (mx, my)
        return task.cont

    def setup_controls(self):
        # Экспорт и Импорт (Новая кнопка F2 для проводника!)
        self.accept("f1", self.save_to_obj)
        self.accept("f2", self.open_obj_explorer)

        self.accept("control-z", self.undo)
        self.accept("control-y", self.redo)

        self.accept("mouse1", self.select_object_under_mouse)
        self.accept("mouse3", self.set_mouse_look, [True])
        self.accept("mouse3-up", self.set_mouse_look, [False])
        
        self.accept("f5", self.spawn_object, ["box"])
        self.accept("f6", self.spawn_object, ["ball"])
        self.accept("f7", self.spawn_object, ["triple box"])
        self.accept("shift-1", self.spawn_object, ["block 4"])
        self.accept("shift-2", self.spawn_object, ["block 8"])
        self.accept("shift-3", self.spawn_object, ["grass platform"])
        self.accept("shift-4", self.spawn_object, ["stone block"])
        self.accept("shift-5", self.spawn_object, ["platform 10x10"])

        self.accept("control-1", self.make_preset_box, [255, 255, 255, None])
        self.accept("control-2", self.make_preset_box, [180, 180, 185, "metal"])
        self.accept("control-3", self.make_preset_box, [139, 69, 19, "wood"])
        self.accept("control-4", self.make_preset_box, [34, 139, 34, "grass"])
        self.accept("control-5", self.make_preset_box, [105, 105, 105, "stone"])
        self.accept("control-6", self.make_preset_box, [255, 0, 0, None])
        self.accept("control-7", self.make_preset_box, [0, 255, 0, None])
        self.accept("control-8", self.make_preset_box, [0, 0, 255, None])

        self.accept("h", self.apply_texture, ["metal"])
        self.accept("j", self.apply_texture, ["wood"])
        self.accept("k", self.apply_texture, ["grass"])
        self.accept("l", self.apply_texture, ["stone"])

        self.accept("arrow_left", self.move_object, [-MOVE_SPEED, 0, 0])
        self.accept("arrow_right", self.move_object, [MOVE_SPEED, 0, 0])
        self.accept("arrow_up", self.move_object, [0, MOVE_SPEED, 0])
        self.accept("arrow_down", self.move_object, [0, -MOVE_SPEED, 0])
        self.accept("page_up", self.move_object, [0, 0, MOVE_SPEED])
        self.accept("page_down", self.move_object, [0, 0, -MOVE_SPEED])

        self.accept("+", self.scale_object_all, [SCALE_SPEED])
        self.accept("=", self.scale_object_all, [SCALE_SPEED])
        self.accept("-", self.scale_object_all, [-SCALE_SPEED])
        self.accept("[", self.scale_object_axis, [-SCALE_SPEED, 0, 0])
        self.accept("]", self.scale_object_axis, [SCALE_SPEED, 0, 0])
        self.accept(";", self.scale_object_axis, [0, -SCALE_SPEED, 0])
        self.accept("'", self.scale_object_axis, [0, SCALE_SPEED, 0])
        self.accept(".", self.scale_object_axis, [0, 0, -SCALE_SPEED])
        self.accept("/", self.scale_object_axis, [0, 0, SCALE_SPEED])

        self.accept("r", self.edit_rgb_255, [-5, 0, 0])
        self.accept("t", self.edit_rgb_255, [5, 0, 0])
        self.accept("f", self.edit_rgb_255, [0, -5, 0])
        self.accept("g", self.edit_rgb_255, [0, 5, 0])
        self.accept("v", self.edit_rgb_255, [0, 0, -5])
        self.accept("b", self.edit_rgb_255, [0, 0, 5])

        self.accept("a", self.move_camera, [-CAM_SPEED, 0, 0])
        self.accept("d", self.move_camera, [CAM_SPEED, 0, 0])
        self.accept("w", self.move_camera, [0, CAM_SPEED, 0])
        self.accept("s", self.move_camera, [0, -CAM_SPEED, 0])
        self.accept("q", self.move_camera, [0, 0, -CAM_SPEED])
        self.accept("e", self.move_camera, [0, 0, CAM_SPEED])
        self.accept("escape", sys.exit)

    def move_object(self, dx, dy, dz):
        if self.active_object:
            self.save_state("move", self.active_object)
            pos = self.active_object.getPos()
            self.active_object.setPos(pos.getX() + dx, pos.getY() + dy, pos.getZ() + dz)

    def scale_object_all(self, factor):
        if self.active_object:
            self.save_state("scale", self.active_object)
            scale = self.active_object.getScale()
            self.active_object.setScale(max(0.1, scale.getX()+factor), max(0.1, scale.getY()+factor), max(0.1, scale.getZ()+factor))

    def scale_object_axis(self, dx, dy, dz):
        if self.active_object:
            self.save_state("scale", self.active_object)
            scale = self.active_object.getScale()
            self.active_object.setScale(max(0.1, scale.getX()+dx), max(0.1, scale.getY()+dy), max(0.1, scale.getZ()+dz))

    def edit_rgb_255(self, dr, dg, db):
        if self.active_object:
            self.r_255 = min(255, max(0, self.r_255 + dr))
            self.g_255 = min(255, max(0, self.g_255 + dg))
            self.b_255 = min(255, max(0, self.b_255 + db))
            self.apply_color()
            self.update_ui_info()

    def move_camera(self, dx, dy, dz):
        cam_pos = self.camera.getPos()
        self.camera.setPos(cam_pos.getX() + dx, cam_pos.getY() + dy, cam_pos.getZ() + dz)

    def save_to_obj(self):
        if not self.active_object: return
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        file_path = os.path.join(desktop_path, "3d_model.obj")
        try:
            with open(file_path, "w") as f:
                f.write(f"# Exported from Infinite Sandbox\n")
                mat = self.active_object.getMat(self.render)
                geom_nodes = self.active_object.findAllMatches("**/+GeomNode")
                for geom_node_path in geom_nodes:
                    node = geom_node_path.node()
                    for i in range(node.getNumGeoms()):
                        geom = node.getGeom(i)
                        vdata = geom.getVertexData()
                        vertex_reader = GeomVertexReader(vdata, "vertex")
                        while not vertex_reader.isAtEnd():
                            v = vertex_reader.getData3f()
                            world_v = mat.xformPoint(v)
                            f.write(f"v {world_v.getX()} {world_v.getZ()} {-world_v.getY()}\n")
                        for j in range(geom.getNumPrimitives()):
                            prim = geom.getPrimitive(j).decompose()
                            for k in range(prim.getNumPrimitives()):
                                s = prim.getPrimitiveStart(k)
                                f.write("f")
                                for p in range(s, prim.getPrimitiveEnd(k)):
                                    f.write(f" {prim.getVertex(p) + 1}")
                                f.write("\n")
            self.update_ui_info(extra_msg="(SAVED TO DESKTOP!)")
        except Exception as e:
            self.update_ui_info(extra_msg="(ERROR!)")

app = Infinite3DStudio()
app.run()