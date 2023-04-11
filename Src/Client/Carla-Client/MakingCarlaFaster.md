# Making Carla Run Faster
## Python API
1) Remove all unnecessary sensors from the code. I removed these sensors:
    - Collision Sensor
    - Lane Invasion Sensor
    - Gnss Sensor
    - Imu Sensor
    - Radar Sensor
2) Load the smallest map Town02_Opt
3) Use the Opt version of the map so you can remove layers. Remove these layers:
```python
world_map.unload_map_layer(carla.MapLayer.Buildings)
world_map.unload_map_layer(carla.MapLayer.Decals)
world_map.unload_map_layer(carla.MapLayer.Foliage)
world_map.unload_map_layer(carla.MapLayer.Ground)
world_map.unload_map_layer(carla.MapLayer.ParkedVehicles)
world_map.unload_map_layer(carla.MapLayer.Particles)
world_map.unload_map_layer(carla.MapLayer.Props)
world_map.unload_map_layer(carla.MapLayer.StreetLights)
world_map.unload_map_layer(carla.MapLayer.Walls)
```

## Server Side
1) When running Carla append these arguments. (RPC option is here just so I remember it):

    `-quality-level=Low -carla-rpc-port=2000`
2) Go into the config folder and edit `DefaultEngine.ini` so that all of the default maps are Town02_Opt.
3) Edit `DefaultGame.ini` and put a `#` in front of the lines that begin with `+MapsToCook...` for all maps except Town02_Opt.
