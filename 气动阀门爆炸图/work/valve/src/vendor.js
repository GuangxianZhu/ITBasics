import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { mergeGeometries, toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";

window.THREE = Object.assign({}, THREE, {
  OrbitControls,
  RoomEnvironment,
  mergeGeometries,
  toCreasedNormals,
});
