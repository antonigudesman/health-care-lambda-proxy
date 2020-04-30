VAGRANTFILE_API_VERSION = "2"

if !File.exist?('provision/local.json')
  puts "You must have a 'local.json' file in the 'provision' directory with the proper credentials."
  puts "See the 'local.json.sample file for instructions."
  #puts "Canceling Vagrant..."
  #exit
end

require 'json'

#local_conf = JSON.parse(File.read("provision/local.json"))


Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.box = "bento/amazonlinux-2"
  config.vm.provision "file", source: "~/.aws/credentials", destination: "/home/vagrant/.aws/credentials"
  config.vm.provision "file", source: "~/.aws/config", destination: "/home/vagrant/.aws/config"
  config.vm.provision :shell, path: "bootstrap.sh"
end