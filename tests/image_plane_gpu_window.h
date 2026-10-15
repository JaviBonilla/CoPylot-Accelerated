#ifndef COPILOT_IMAGE_PLANE_GPU_WINDOW_H
#define COPILOT_IMAGE_PLANE_GPU_WINDOW_H
#include <algorithm>
#include <cstdio>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
// Optional preliminary-timing guard, synchronous and outside every measured interval.
class ImagePlaneGpuWindow {
    std::set<int> allowed_;
    bool initialized_=false;
    static std::string command(const char* cmd) {
        FILE* pipe=popen(cmd,"r");if (!pipe) throw std::runtime_error("Cannot query GPU timing window");
        std::string text;char line[512];while (fgets(line,sizeof(line),pipe)) text+=line;
        if (pclose(pipe)!=0) throw std::runtime_error("GPU timing-window query failed");
        return text;
    }
    std::set<int> processes() {
        std::istringstream rows(command("nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits"));
        std::set<int> result;std::string line;
        while (std::getline(rows,line)) {
            if (line.find_first_not_of(" \t\r")==std::string::npos) continue;
            std::istringstream entry(line);int pid;
            if (!(entry>>pid) || pid<=0) throw std::runtime_error("Invalid GPU process query");
            result.insert(pid);
        }
        return result;
    }
    void telemetry(bool initial) {
        auto text=command("nvidia-smi --query-gpu=memory.used,utilization.gpu,temperature.gpu --format=csv,noheader,nounits");
        std::replace(text.begin(),text.end(),',',' ');std::istringstream row(text);
        int memory,utilization,temperature;
        if (!(row>>memory>>utilization>>temperature)) throw std::runtime_error("Invalid GPU timing-window telemetry");
        if (memory>(initial?128:4096) || temperature>=80 || (initial && utilization!=0))
            throw std::runtime_error("GPU timing window rejected: memory_mib="+std::to_string(memory)+", utilization_pct="+std::to_string(utilization)+", temperature_c="+std::to_string(temperature)+", initial="+std::to_string(initial));
        maximum_memory_mib=std::max(maximum_memory_mib,memory);maximum_temperature_c=std::max(maximum_temperature_c,temperature);++checks;
    }
public:
    int checks=0,maximum_memory_mib=0,maximum_temperature_c=0;
    void begin() {
        if (!processes().empty()) throw std::runtime_error("External GPU process present before preliminary timing");
        telemetry(true);
    }
    void check() {
        const auto now=processes();
        if (!initialized_) { if (now.size()!=1) throw std::runtime_error("Expected exactly one owned GPU process after warmup");allowed_=now;initialized_=true; }
        else if (now!=allowed_) throw std::runtime_error("GPU processes changed during preliminary timing");
        telemetry(false);
    }
};
#endif
