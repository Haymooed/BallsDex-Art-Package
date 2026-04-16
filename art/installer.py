import os
import requests
import yaml

async def install():
    msg = await ctx.send("Starting installation of the Art Package...")
    
    repo_api = "https://api.github.com/repos/Haymooed/BallsDex-Art-Package/contents/art"
    headers = {"Accept": "application/vnd.github.v3+json"}
    
    try:
        req = requests.get(repo_api, headers=headers)
        req.raise_for_status()
        files = req.json()
    except Exception as e:
        return await msg.edit(content=f"❌ Failed to fetch repo contents: {e}")
        
    os.makedirs("ballsdex/packages/art", exist_ok=True)
    
    for f in files:
        if f["type"] == "file":
            file_data = requests.get(f["download_url"]).content
            with open(f"ballsdex/packages/art/{f['name']}", "wb") as out:
                out.write(file_data)
                
    # Update config.yml
    config_path = "config.yml"
    if os.path.exists(config_path):
        with open(config_path, "r") as conf_file:
            config = yaml.safe_load(conf_file) or {}
            
        packages = config.get("packages",[])
        if "ballsdex.packages.art" not in packages:
            packages.append("ballsdex.packages.art")
            config["packages"] = packages
            with open(config_path, "w") as conf_file:
                yaml.dump(config, conf_file, sort_keys=False)
                
    # Reload bot extensions
    try:
        await bot.reload_extension("ballsdex.packages.art")
    except Exception:
        await bot.load_extension("ballsdex.packages.art")
        
    await ctx.invoke(bot.get_command("reloadtree"))
    await msg.edit(content="✅ **Ballsdex Art Package** installed successfully!\nYou can configure it in `ballsdex/packages/art/config.toml`.")

await install()
